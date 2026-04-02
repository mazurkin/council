import asyncio
import json
import logging
import pathlib
import typing as t

import acp
import acp.client.connection
import acp.schema


# noinspection PyProtocol
class _ChatClient(acp.Client):
    """ACP client implementation that collects agent message chunks into a response buffer."""

    def __init__(self, label: str = 'agent'):
        # label for logging streamed chunks
        self.label: str = label
        # accumulated response text from agent message chunks
        self.response_parts: list[str] = []

    async def session_update(
        self,
        session_id: str,
        update: t.Any,
        **kwargs: t.Any,
    ) -> None:
        """Handles session update notifications, collecting text from agent message chunks.

        :param session_id: the session identifier
        :param update: the session update payload (agent message chunk, tool call, etc.)
        """
        if isinstance(update, acp.schema.AgentMessageChunk):
            if isinstance(update.content, acp.schema.TextContentBlock):
                self.response_parts.append(update.content.text)
                logging.debug('[%s] chunk: %s', self.label, update.content.text[:80])

    async def request_permission(self, **kwargs: t.Any) -> acp.schema.RequestPermissionResponse:
        """Not supported — raises method_not_found."""
        raise acp.RequestError.method_not_found('session/request_permission')

    async def write_text_file(self, **kwargs: t.Any) -> acp.schema.WriteTextFileResponse | None:
        """Not supported — raises method_not_found."""
        raise acp.RequestError.method_not_found('fs/write_text_file')

    async def read_text_file(self, **kwargs: t.Any) -> acp.schema.ReadTextFileResponse:
        """Not supported — raises method_not_found."""
        raise acp.RequestError.method_not_found('fs/read_text_file')

    async def create_terminal(self, **kwargs: t.Any) -> acp.schema.CreateTerminalResponse:
        """Not supported — raises method_not_found."""
        raise acp.RequestError.method_not_found('terminal/create')

    async def terminal_output(self, **kwargs: t.Any) -> acp.schema.TerminalOutputResponse:
        """Not supported — raises method_not_found."""
        raise acp.RequestError.method_not_found('terminal/output')

    async def release_terminal(self, **kwargs: t.Any) -> acp.schema.ReleaseTerminalResponse | None:
        """Not supported — raises method_not_found."""
        raise acp.RequestError.method_not_found('terminal/release')

    async def wait_for_terminal_exit(self, **kwargs: t.Any) -> acp.schema.WaitForTerminalExitResponse:
        """Not supported — raises method_not_found."""
        raise acp.RequestError.method_not_found('terminal/wait_for_exit')

    async def kill_terminal(self, **kwargs: t.Any) -> acp.schema.KillTerminalResponse | None:
        """Not supported — raises method_not_found."""
        raise acp.RequestError.method_not_found('terminal/kill')

    async def ext_method(self, method: str, params: dict[str, t.Any]) -> dict[str, t.Any]:
        """Not supported — raises method_not_found."""
        raise acp.RequestError.method_not_found(method)

    async def ext_notification(self, method: str, params: dict[str, t.Any]) -> None:
        """Ignores extension notifications."""

    def on_connect(self, conn: acp.Agent) -> None:
        """Called when the connection to the agent is established."""

    def get_response(self) -> str:
        """Returns the accumulated response text.

        :return: the full response text joined from all agent message chunks
        """
        return ''.join(self.response_parts)


class AcpClient:
    """ACP client for a single agent that keeps the connection open across multiple prompts."""

    # directory for persisting per-agent session files
    COUNCIL_DIR: t.Final[str] = '.council'

    # increased buffer limit for asyncio.StreamReader (16 MB), the default 64 KB
    # is too small for large ACP messages from the Copilot CLI server
    STREAM_LIMIT: t.Final[int] = 16 * 1024 * 1024

    def __init__(self, host: str, port: int, agent_name: str, folder: pathlib.Path):
        """Creates an ACP client for a specific agent.

        Call :meth:`connect` before sending prompts and :meth:`close` when done.

        :param host: the hostname or IP address of the Copilot CLI server
        :param port: the TCP port of the Copilot CLI server
        :param agent_name: the agent name used as a key for session tracking
        :param folder: the working directory to use for agent sessions
        """
        assert folder.is_dir(), f'folder does not exist: {folder}'

        self.host: t.Final[str] = host
        self.port: t.Final[int] = port
        self.agent_name: t.Final[str] = agent_name
        self.folder: t.Final[str] = str(folder)

        # per-agent session persistence file: .council/{agent_name}.json
        self.session_path: t.Final[pathlib.Path] = folder / self.COUNCIL_DIR / 'sessions' / f'{agent_name}.json'
        self.session_path.parent.mkdir(parents=True, exist_ok=True)

        # chat client for collecting response chunks
        self.chat_client: _ChatClient = _ChatClient(label=agent_name)

        # connection state, initialized in connect()
        self.session_id: str | None = None
        self.connection: acp.client.connection.ClientSideConnection | None = None
        self.writer: asyncio.StreamWriter | None = None

    async def connect(self, reset: bool = False) -> None:
        """Opens the TCP connection, initializes ACP, and creates or resumes a session.

        Must be called before :meth:`chat_async`.

        :param reset: if True, always create a new session instead of resuming a saved one
        """
        label: str = self.agent_name

        logging.info('[%s] connecting to %s:%s...', label, self.host, self.port)

        # open TCP connection to the Copilot CLI server
        reader, writer = await asyncio.open_connection(self.host, self.port, limit=self.STREAM_LIMIT)
        self.writer = writer
        logging.info('[%s] connected', label)

        # create ACP client-side connection (input_stream=writer, output_stream=reader)
        self.connection = acp.connect_to_agent(
            client=self.chat_client,
            input_stream=writer,
            output_stream=reader,
        )

        # initialize the ACP protocol
        await self.connection.initialize(protocol_version=acp.PROTOCOL_VERSION)

        # resume existing session or create a new one
        existing_session_id: str | None = None if reset else self._load_session()

        if existing_session_id is not None:
            logging.info('[%s] loading session %s', label, existing_session_id)
            await self.connection.load_session(cwd=self.folder, session_id=existing_session_id)
            self.session_id = existing_session_id
        else:
            logging.info('[%s] creating new session', label)
            session_response: acp.schema.NewSessionResponse = await self.connection.new_session(cwd=self.folder)
            self.session_id = session_response.sessionId
            self._save_session()
            logging.info('[%s] session created: %s', label, self.session_id)

        # ask the agent to re-read the instructions
        hello_prompt: str = (
            'Council has started the new work session. Re-read the content of AGENTS.md. '
            'Standby now, wait and be prepared for the next requests.'
        )
        hello_response: str = await self.chat_async(hello_prompt)

        logging.info('[%s] session initialized: %s', label, hello_response)

    async def close(self) -> None:
        """Closes the ACP connection and the underlying TCP connection."""
        label: str = self.agent_name

        if self.connection is not None:
            await self.connection.close()
            self.connection = None

        if self.writer is not None:
            self.writer.close()
            await self.writer.wait_closed()
            self.writer = None

        logging.info('[%s] connection closed', label)

    def _load_session(self) -> str | None:
        """Loads the session id from the per-agent persistence file.

        :return: the session id, or None if no saved session exists
        """
        if not self.session_path.exists():
            return None

        try:
            data: dict[str, str] = json.loads(self.session_path.read_text(encoding='utf-8'))
            session_id: str | None = data.get('session_id')

            if session_id is not None:
                logging.info('[%s] loaded session %s from %s', self.agent_name, session_id, self.session_path)

            return session_id
        except (json.JSONDecodeError, OSError) as e:
            logging.warning('[%s] failed to load session from %s: %s', self.agent_name, self.session_path, e)
            return None

    def _save_session(self) -> None:
        """Saves the current session id to the per-agent persistence file."""
        try:
            text: str = json.dumps({'session_id': self.session_id}, indent=2)
            self.session_path.write_text(text, encoding='utf-8')

            logging.debug('[%s] saved session to %s', self.agent_name, self.session_path)
        except OSError as e:
            logging.warning('[%s] failed to save session to %s: %s', self.agent_name, self.session_path, e)

    async def chat_async(self, prompt: str) -> str:
        """Sends a prompt to the agent and returns the response text.

        :meth:`connect` must be called before this method.

        :param prompt: the text prompt to send to the agent
        :return: the agents complete text response
        """
        assert self.connection is not None, 'not connected, call connect() first'
        assert self.session_id is not None, 'no session, call connect() first'

        label: str = self.agent_name

        # reset response buffer for this prompt
        self.chat_client.response_parts.clear()

        # send the prompt and wait for the response
        logging.info('[%s] sending prompt (%s chars)', label, len(prompt))
        await self.connection.prompt(
            prompt=[acp.text_block(prompt)],
            session_id=self.session_id,
        )

        response: str = self.chat_client.get_response()
        logging.info('[%s] response received (%s chars)', label, len(response))

        return response
