"""Unit tests for the state-aware agent actions (src/ai/agent.py).

Run with: python3 -m unittest discover -s tests -v   (or `make test`)
"""

import unittest

from src.ai import agent as agent_mod
from src.ai.agent import VacuumAgent
from src.home_connect.client import HomeConnectError

OPERATION_READY = agent_mod.OPERATION_READY
OPERATION_RUN = agent_mod.OPERATION_RUN
OPERATION_PAUSE = agent_mod.OPERATION_PAUSE

STATUS_OPERATION = agent_mod.STATUS_OPERATION


def op_status(operation: str) -> list[dict]:
    return [{"key": STATUS_OPERATION, "value": operation}]


def wrong_state_error(what: str = "start cleaning") -> HomeConnectError:
    """A 409 SDK.Error.WrongOperationState like the real BCRD2W returns."""
    return HomeConnectError(
        f"PUT https://api.home-connect.com/api/homeappliances/1/programs/active -> 409: "
        f'{{"error": {{"description": "Request cannot be performed since OperationState '
        f'is not Ready", "key": "SDK.Error.WrongOperationState"}}}}'
    )


class FakeLLM:
    """Returns a fixed raw model reply (a JSON decision)."""

    def __init__(self, raw: str):
        self._raw = raw

    def chat(self, messages):
        return self._raw


class FakeClient:
    """In-memory HomeConnectClient double that records what the agent asks it to do."""

    def __init__(self, operation, start_error=None, resume_error=None, stop_error=None):
        self.operation = operation
        self.start_error = start_error
        self.resume_error = resume_error
        self.stop_error = stop_error
        self.started = False
        self.resumed = False
        self.stopped = False

    def get_status(self, ha_id):
        return op_status(self.operation)

    def start_program(self, ha_id, key):
        if self.start_error:
            raise self.start_error
        self.started = True
        self.operation = OPERATION_RUN

    def execute_command(self, ha_id, commandkey, value=True):
        if commandkey != "BSH.Common.Command.ResumeProgram":
            raise AssertionError(f"unexpected command: {commandkey}")
        if self.resume_error:
            raise self.resume_error
        self.resumed = True
        self.operation = OPERATION_RUN

    def stop_program(self, ha_id):
        if self.stop_error:
            raise self.stop_error
        self.stopped = True
        self.operation = OPERATION_READY


def agent_for(client: FakeClient) -> VacuumAgent:
    return VacuumAgent(client, llm=FakeLLM('{"action": "start", "reply": ""}'))


class AgentStartTest(unittest.TestCase):
    def test_start_when_ready_starts_cleaning(self):
        client = FakeClient(OPERATION_READY)
        reply = agent_for(client).run("1", "start cleaning")
        self.assertTrue(client.started)
        self.assertFalse(client.resumed)
        self.assertIn("Started cleaning", reply)

    def test_start_when_paused_resumes_instead(self):
        client = FakeClient(OPERATION_PAUSE)
        reply = agent_for(client).run("1", "start cleaning")
        self.assertTrue(client.resumed)
        self.assertFalse(client.started)
        self.assertIn("resumed cleaning", reply.lower())

    def test_start_when_already_running_is_noop(self):
        client = FakeClient(OPERATION_RUN)
        reply = agent_for(client).run("1", "start cleaning")
        self.assertFalse(client.started)
        self.assertFalse(client.resumed)
        self.assertIn("already cleaning", reply.lower())

    def test_start_409_wrong_state_is_friendly_not_a_traceback(self):
        client = FakeClient(OPERATION_READY, start_error=wrong_state_error())
        agent = VacuumAgent(client, llm=FakeLLM('{"action": "start", "reply": ""}'))
        reply = agent.run("1", "start cleaning")
        self.assertFalse(client.started)
        self.assertIn("could not start cleaning", reply)
        self.assertIn("Ready", reply)  # current state is named in the hint


class AgentStopTest(unittest.TestCase):
    def test_stop_when_cleaning_stops(self):
        client = FakeClient(OPERATION_RUN)
        agent = VacuumAgent(client, llm=FakeLLM('{"action": "stop", "reply": ""}'))
        reply = agent.run("1", "stop cleaning")
        self.assertTrue(client.stopped)
        self.assertIn("Stopped cleaning", reply)

    def test_stop_when_idle_is_noop(self):
        client = FakeClient(OPERATION_READY)
        agent = VacuumAgent(client, llm=FakeLLM('{"action": "stop", "reply": ""}'))
        reply = agent.run("1", "stop cleaning")
        self.assertFalse(client.stopped)
        self.assertIn("nothing to stop", reply.lower())


class AgentStatusTest(unittest.TestCase):
    def test_status_returns_a_reply(self):
        client = FakeClient(OPERATION_READY)
        agent = VacuumAgent(client, llm=FakeLLM('{"action": "status", "reply": "idle"}'))
        self.assertIn("idle", agent.run("1", "what is the state?"))


if __name__ == "__main__":
    unittest.main()
