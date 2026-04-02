import asyncio
import datetime
import shutil

import pydantic
import argh
import pathlib
import logging
import logging.config
import typing as t
import yaml
import sys
import json
import enum

import acp_client

_COUNCIL_COMMON_PROMPT: str = '''This is the multi-agent "council" system.

Council has multiple agents playing three different roles (in order of appearance):
- "critic", single agent, the manager, the boss, the coordinator, who estimates and evaluates the work done by the "innovators" on the previous step, ideas from the "dreamer", and make directions for the current step.
- "innovators", multiple agents who execute actions to solve the problem defined by the user.
- "dreamer", single agent, who is brainstorming without doing anything itself
- "clerk", single agent, who documents the whole process for the user, result from the "innovators", ideas from the "dreamer" and summary made by the "critic".

Council works in "steps" (iterations), in every step the external orchestrator sequentially asks all the "critic",
the "innovators", the "dreamer", and finally it asks the "clerk".

After this step the orchestrator starts the next similar step, and then the next step, and so on.

The previous reports are stored in `.council/reports` folder, as well as the reports of the others,
so you can read all previous reports of all council members at any time.

You do not need to save your individual report yourself, it will be saved by the external orchestrator
to the `.council/reports` folder. Just put the all report information to the output.

On every step step you must read the following files:
- read the problem description defined by the user from the `.council/problem.md` file.
- read the global knowledge base from the `.council/knowledge.md` file, updated by the "clerk" on the previous step.

On every step step you could read the following files:
- read the latest reports from everyone, especially from the "clerk" from the `.council/reports` folder.

The reports of every step, each step is named by the timestamp when it started:
- `.council/reports/**/problem-snapshot.md` - the latest copy of the `.council/problem.md` file with the problem description for the protocol
- `.council/reports/**/critic.md` - the report from the "critic" in the beginning of the step
- `.council/reports/**/innovators.md` - the report from the "innovators"
- `.council/reports/**/dreamer.md` - brainstorming report from the "dreamer"
- `.council/reports/**/clerk.md` - final summary from the "clerk" in the end of the step

Refer to the instructions in the `AGENTS.md` in the root of the project.

Do not use any interaction as the communication is automatic and there is no one to respond to the questions.
'''

@pydantic.dataclasses.dataclass(frozen=True)
class CouncilRoleDescription:

    name: str

    prompt: str


class CouncilRole(enum.Enum):

    CRITIC = CouncilRoleDescription(
        name='critic',
        prompt=(
            f'{_COUNCIL_COMMON_PROMPT}'

            '\n\n'

            'You play the "critic" role in the council workflow, '
            'review the previous reports from "innovators", analyse them and put your detailed review. '

            '\n\n'

            'Analyse and estimate the ideas and the results of the "innovators" and find the reasons '
            'why every idea and result is good and bad.'

            '\n\n'

            'Make your own ideas and suggestions.'

            '\n\n'

            'Analyse the problem and feedback from the user and make decisions how to improve the process.'

            '\n\n'

            'Do not do the work yourself, just check the reports and make your comments about the process.'

            '\n\n'

            'If there are multiple ideas, you must set the priorities, consider simple and easy-to-check ideas first. '
            'Do not let the "innovators" to generate too many ideas without checking. '
            'Try to focus on one idea at time, do not allow spreading activity on too many unrelated problems at once.'

            '\n\n'

            'Check if the "innovators" actually followed your instructions made on the previous step.'

            '\n\n'

            'It is acceptable and even encouraging if the "innovators" do the same work simultaneously. '
            'It allows you to compare and verify the results. '

            '\n\n'

            'If there is some discrepancy between the "innovators" either find the reason for discrepancy yourself, '
            'or force the "innovators" find the right way themselves and come to consensus.'

            '\n\n'

            'Encourage the "innovators" to move in small steps, so you could estimate the made progress '
            'and the step result immediately and the whole council could move to the next step (iteration) '
            'with the updated instructions.'

            '\n\n'

            'Listen to what the "dreamer" says but be realistic. The job of the "dreamer" is to brainstorm '
            'and think out-of-the-box. Your job is to deliver and be practical. Do no try to control and '
            'instruct the "dreamer" it is an independent actor whos act as a consultant but not an executor.'

            '\n\n'

            'If you have confidence on something make a clear direct instruction to the "innovators" '
            'what to do and what to not do. Make clear and consistent conclusions and commands. '
        )
    )

    INNOVATOR = CouncilRoleDescription(
        name='innovator',
        prompt=(
            f'{_COUNCIL_COMMON_PROMPT}'

            '\n\n'

            'You play the "innovator" role in the council workflow, '
            'check the last "clerk" report(s) and the description of the problem '
            'and make your research and execute actions to solve the problem. '

            '\n\n'

            'Your role is to make the new ideas for the experiments base on the initial task given by the user '
            'and implement them using all available tool and knowledge in this project. '

            '\n\n'

            'If some description in documentation is wrong you must mention that, so the user could intervene and '
            'fix the discrepancy in the documentation.'

            '\n\n'

            'Suggest any idea which could work. But do not generate new ideas if you have enough open ideas already. '
            'It is better to move in small step iterations, confirming the result with '
            'the "critic" and interchanging the ideas with the other "inventors".'

            '\n\n'

            '"Fail fast ©". '

            '\n\n'

            'Get familiar the summary made by the "clerk" on the previous step as there will be instructions and '
            'the important feedback from the "critic". '

            '\n\n'

            'Listen to the advices of the "critic" and do follow them. Especially follow the instructions '
            'from the "critic" provided in the latest report. '
            'Check the comments and instructions which are related to your own agent name.'

            '\n\n'

            'If you need to run the Python code you can do it using the Conda environment with the name "council" '
            'which has `pandas`, `numpy`, `catboost`, `xgboost`, `vowpalwabbit`, `scikit-learn`, `hdbscan`, '
            '`statsmodels`, `datasketches` and the other libraries.'

            '\n\n'

            'Example how to run Python:' '\n'
            '```shell' '\n'
            'conda run --no-capture-output --live-stream --name council python3 example.py' '\n'
            '```'

            '\n\n'

            'When you run Python script or any other command I suggest to use pipelining to `tee` utility '
            'so the logs at the same time available to you for analysis and stored to the disk for the user. '
            'Also it could help if the script of the command fails. '

            '\n\n'

            'Make the final clean and detailed report for the review of the "critic":' '\n'
            '- what was your idea(s)' '\n'
            '- what have you done to check it (facts)' '\n'
            '- what went well and what went badly (facts)' '\n'
            '- what is the result (facts)' '\n'
            '- where are all artefacts (example: files) you made and saved during the step (facts)' '\n'
            '- what do you think about the result (opinion)' '\n'
            '- what could you suggest as the next step (ideas)' '\n'

            '\n\n'

            'Do not stop early even if the result is ready. Use all given step to improve it. '
            'Brainstorm, generate the ideas and check them with implementation.'

            '\n\n'

            'If you are unsure about something, make a comment and let the "critic" to decide.'

            '\n\n'

            'Use the provided step name/id and your own name in the names of the work files/queries/documents '
            'to avoid the file conflict with the other innovators. '
            'Create a subfolder with the name of this step and your own agent name '
            'and you put all you work for this step into this subfolder.'
        )
    )

    DREAMER = CouncilRoleDescription(
        name='dreamer',
        prompt=(
            f'{_COUNCIL_COMMON_PROMPT}'

            '\n\n'

            'You play the "dreamer" role in the council workflow, '
            'review the work done by the "innovators" and the analysis made by the "critic".'

            '\n\n'

            'You task is to think out-of-the-box. No idea is too big. No improvement is too small.'

            '\n\n'

            'Do **not** do any work yourself. You job is to brainstorm, generate new ideas and look into the future.'

            '\n\n'

            'Be independent, you do not have to follow the instruction from the "critic".'

            '\n\n'

            'Make new ideas, invent new approaches, suggest new methods, be creative.'
        )
    )

    CLERK = CouncilRoleDescription(
        name='clerk',
        prompt=(
            f'{_COUNCIL_COMMON_PROMPT}'

            '\n\n'

            'You play the "clerk" role in the council workflow, '
            'review the work done by the "innovators" and the analysis made by the "critic", '
            'make the summary and put the summary into the report. '

            '\n\n'

            'Make the report well-structured, readable, detailed report based on the information '
            'from the "innovators" and the analysis made by the "critic".'

            '\n\n'

            'Do not miss the important details. '
            'The information from the report will be used by the "innovators" on the next step.'
            'Pay special attention to the specific instructions from the "critic", '
            'these instruction are very important for the "innovators" as they must follow them on the next step.'

            '\n\n'

            'Manage, update and actualize all the global knowledge base file in the `.council/knowledge.md` file. '
            'Make the information in the knowledge base to reflect the current progress, process and the results. '
            'Do not leave any outdated information there. '

            '\n\n'

            'In the knowledge base keep track of all and the best scores, metrics and hyperparameters.'
        )
    )

    @property
    def descriptor(self) -> CouncilRoleDescription:
        return self.value


@pydantic.dataclasses.dataclass(frozen=True)
class CouncilAgent:

    name: str

    role: CouncilRole

    host: str

    port: int


class Council:

    AGENT_INNOVATORS: list[CouncilAgent] = [
        CouncilAgent(
            name='innovator-1',
            role=CouncilRole.INNOVATOR,
            host='127.0.0.1',
            port=10001,
        ),
        CouncilAgent(
            name='innovator-2',
            role=CouncilRole.INNOVATOR,
            host='127.0.0.1',
            port=10002,
        ),
    ]

    AGENT_CRITIC: CouncilAgent = CouncilAgent(
        name='critic',
        role=CouncilRole.CRITIC,
        host='127.0.0.1',
        port=10003,
    )

    AGENT_CLERK: CouncilAgent = CouncilAgent(
        name='clerk',
        role=CouncilRole.CLERK,
        host='127.0.0.1',
        port=10004,
    )

    AGENT_DREAMER: CouncilAgent = CouncilAgent(
        name='dreamer',
        role=CouncilRole.DREAMER,
        host='127.0.0.1',
        port=10005,
    )

    def __init__(
        self,
        project_folder_path: pathlib.Path,
    ):
        assert project_folder_path.is_dir(), 'project folder does not exist: ' + str(project_folder_path)
        self.project_folder_path: t.Final[pathlib.Path] = project_folder_path

        self.council_root_folder_path: t.Final[pathlib.Path] = self.project_folder_path / '.council'
        self.council_root_folder_path.mkdir(parents=True, exist_ok=True)

        self.council_report_folder_path: t.Final[pathlib.Path] = self.council_root_folder_path / 'reports'
        self.council_report_folder_path.mkdir(parents=True, exist_ok=True)

        # per-agent ACP clients, keyed by agent name
        self.clients: t.Final[dict[str, acp_client.AcpClient]] = {}

        for agent in (*self.AGENT_INNOVATORS, self.AGENT_CRITIC, self.AGENT_CLERK, self.AGENT_DREAMER):
            assert agent.name not in self.clients, 'duplicate name: ' + agent.name

            self.clients[agent.name] = acp_client.AcpClient(
                host=agent.host,
                port=agent.port,
                agent_name=agent.name,
                folder=project_folder_path,
            )

    async def connect(self, reset: bool = False) -> None:
        """Connects all agent clients in parallel.

        :param reset: if True, create new sessions instead of resuming saved ones
        """
        await asyncio.gather(
            *(
                client.connect(reset=reset)
                for client in self.clients.values()
            )
        )

    async def close(self) -> None:
        """Closes all agent clients in parallel."""
        await asyncio.gather(
            *(
                client.close()
                for client in self.clients.values()
            )
        )

    async def step(self, step_idx: int, step_cnt: int):
        """Runs the council loop: queries all innovator agents in parallel and collects responses.

        :return: a map of agent name to the agent's response text
        """

        # a unique tag for the step
        step_tag: str = datetime.datetime.now().strftime('%Y%m%d-%H%M%S')
        logging.info('start step %s', step_tag)

        # final step?
        final_step: bool = step_idx == step_cnt

        # create a new report folder
        council_step_folder_path: pathlib.Path = self.council_report_folder_path / step_tag
        council_step_folder_path.mkdir(parents=True, exist_ok=True)

        # make a copy of the problem
        shutil.copy(
            src=self.council_root_folder_path / 'problem.md',
            dst=council_step_folder_path / 'problem-snapshot.md',
            follow_symlinks=True,
        )

        # ---------------------------------------------------------------------
        # load the latest report
        # ---------------------------------------------------------------------

        # find the last clerk's report
        council_last_clerk_paths: list[pathlib.Path] = sorted(
            self.council_report_folder_path.glob('**/clerk.md'),
            reverse=True,
        )

        if len(council_last_clerk_paths) > 0:
            clerk_last_report_path: pathlib.Path = council_last_clerk_paths[0]
            logging.info('found the previous report at %s', clerk_last_report_path)

            clerk_last_report_text: str = clerk_last_report_path.read_text(encoding='utf-8', errors='strict')

            clerk_last_report: str = (
                f'the report folder of the previous step (iteration): {clerk_last_report_path.parent}'

                '\n\n'

                f'{clerk_last_report_text}'
            )
        else:
            clerk_last_report: str = (
                'This is the very first step in the whole workflow, there is no any previous report from the "clerk".'

                '\n\n'

                'Read the problem definition. '
            )

        # ---------------------------------------------------------------------
        # critic
        # ---------------------------------------------------------------------

        logging.info('asking the critic')

        if not final_step:
            critics_prompts: str = (
                f'Step {step_idx + 1} from {step_cnt} "{step_tag}". '

                f'Your name is "{self.AGENT_CRITIC.name}".\n\n'
                f'{self.AGENT_CRITIC.role.descriptor.prompt}\n\n'

                f'{clerk_last_report}\n'
            )
        else:
            critics_prompts: str = (
                'This is the last step in this session, the "innovators" and the "dreamer" will **NOT** be run. '
                'This is the time to analyse everything, make the final report and suggest ideas for the next session.'

                f'Your name is "{self.AGENT_CRITIC.name}".\n\n'
                f'{self.AGENT_CRITIC.role.descriptor.prompt}\n\n'

                f'{clerk_last_report}\n'
            )

        critics_response: str = await self.clients[self.AGENT_CRITIC.name].chat_async(
            prompt=critics_prompts,
        )

        critics_report: str = (
            '***\n'
            f'*** START OF CRITIC REPORT {step_tag} ***\n'
            '***\n\n'

            f'{critics_response}\n\n'

            '***\n'
            f'*** END OF CRITIC REPORT {step_tag} ***\n'
            '***\n\n'
        )

        council_step_critic_path: t.Final[pathlib.Path] = council_step_folder_path / 'critic.md'
        council_step_critic_path.write_text(critics_report, encoding='utf-8')

        # ---------------------------------------------------------------------
        # innovators (skipped on the final step)
        # ---------------------------------------------------------------------

        if not final_step:
            logging.info('asking the innovators')

            innovator_results: tuple[str] = await asyncio.gather(
                *(
                    self.clients[agent.name].chat_async(
                        prompt=(
                            f'Step {step_idx + 1} from {step_cnt} "{step_tag}". '
                            f'Your name is "{agent.name}".\n\n'
                            f'{agent.role.descriptor.prompt}\n\n'
                            f'{critics_report}\n\n'
                            f'{clerk_last_report}\n'
                        )
                    )
                    for agent in self.AGENT_INNOVATORS
                )
            )

            innovator_ideas: dict[str, str] = {
                agent.name: result
                for agent, result in zip(self.AGENT_INNOVATORS, innovator_results)
            }

            innovator_report: str = ''.join(
                str(
                    '***\n'
                    f'*** START OF INNOVATOR "{k}" REPORT {step_tag} ***\n'
                    '***\n\n'

                    f'{v}\n\n'

                    '***\n'
                    f'*** END OF INNOVATOR "{k}" REPORT {step_tag} ***\n'
                    '***\n\n'
                )
                for k, v in innovator_ideas.items()
            )

            council_step_innovators_path: t.Final[pathlib.Path] = council_step_folder_path / 'innovators.md'
            council_step_innovators_path.write_text(innovator_report, encoding='utf-8')
        else:
            innovator_report: str = ''

        # ---------------------------------------------------------------------
        # dreamer (skipped on the final step)
        # ---------------------------------------------------------------------

        logging.info('asking the dreamer')

        if not final_step:
            dreamer_prompt: str = (
                f'Step {step_idx + 1} from {step_cnt} "{step_tag}". '

                f'Your name is "{self.AGENT_DREAMER.name}".\n\n'
                f'{self.AGENT_DREAMER.role.descriptor.prompt}\n\n'

                f'{critics_report}\n\n'
                f'{innovator_report}\n\n'
            )

            dreamer_response: str = await self.clients[self.AGENT_DREAMER.name].chat_async(
                prompt=dreamer_prompt,
            )

            dreamer_report: str = (
                '***\n'
                f'*** START OF DREAMER REPORT {step_tag} ***\n'
                '***\n\n'

                f'{dreamer_response}\n\n'

                '***\n'
                f'*** END OF DREAMER REPORT {step_tag} ***\n'
                '***\n\n'
            )

            dreamer_step_clerk_path: t.Final[pathlib.Path] = council_step_folder_path / 'dreamer.md'
            dreamer_step_clerk_path.write_text(dreamer_report, encoding='utf-8')
        else:
            dreamer_report: str = ''

        # ---------------------------------------------------------------------
        # clerk for the summary
        # ---------------------------------------------------------------------

        logging.info('asking the clerk')

        if not final_step:
            clerk_prompt: str = (
                f'Step {step_idx + 1} from {step_cnt} "{step_tag}". '

                f'Your name is "{self.AGENT_CLERK.name}".\n\n'
                f'{self.AGENT_CLERK.role.descriptor.prompt}\n\n'

                f'{critics_report}\n\n'
                f'{innovator_report}\n\n'
                f'{dreamer_report}\n\n'
            )
        else:
            clerk_prompt: str = (
                'This is the last step in this session, the "innovators" and the "dreamer" did NOT run. '
                'This is the time to analyse everything, make the final report and suggest ideas for the next session. '

                'Make the final thorough groom of the `.council/knowledge.md` file. '

                f'Your name is "{self.AGENT_CLERK.name}".\n\n'
                f'{self.AGENT_CLERK.role.descriptor.prompt}\n\n'

                f'{critics_report}\n\n'
            )

        clerk_response: str = await self.clients[self.AGENT_CLERK.name].chat_async(
            prompt=clerk_prompt,
        )

        clerk_report: str = (
            '***\n'
            f'*** START OF CLERK REPORT {step_tag} ***\n'
            '***\n\n'

            f'{clerk_response}\n\n'

            '***\n'
            f'*** END OF CLERK REPORT {step_tag} ***\n'
            '***\n\n'
        )

        council_step_clerk_path: t.Final[pathlib.Path] = council_step_folder_path / 'clerk.md'
        council_step_clerk_path.write_text(clerk_report, encoding='utf-8')

        # ---------------------------------------------------------------------
        # end of the step
        # ---------------------------------------------------------------------

        logging.info('clerk says:\n%s', clerk_response)


# noinspection DuplicatedCode,PyMethodMayBeStatic
class CouncilApplication:
    """
    model builder application
    """

    PATH_APPLICATION: t.Final[pathlib.Path] = pathlib.Path(__file__)

    PATH_DIR_SOURCES: t.Final[pathlib.Path] = PATH_APPLICATION.parent.resolve()

    PATH_DIR_PACKAGE: t.Final[pathlib.Path] = PATH_DIR_SOURCES.parent.resolve()

    PATH_DIR_WORK: t.Final[pathlib.Path] = PATH_DIR_PACKAGE / 'work'

    def __init__(self):
        # initialize logging
        logging_config_path: pathlib.Path = self.PATH_DIR_SOURCES / 'council.yaml'
        logging_config = self.load_yaml(logging_config_path, yaml.SafeLoader)
        logging.config.dictConfig(logging_config)
        logging.info('using logging configuration [%s]', logging_config_path)

        # local logger
        self.logger = logging.getLogger('application')
        self.logger.info('command line :\n%s', json.dumps(sys.argv[1:], default=str, indent=2, sort_keys=False))

    @argh.arg('--folder', required=True, type=str, help='Path to the project folder')
    @argh.arg('--steps', required=False, type=int, help='Number of the steps')
    @argh.arg('--reset', required=False, dest='reset', action='store_true', help='start the new session instead of using the last one')
    def run(
        self,
        folder: str = None,
        steps: int = 1,
        reset: bool = False,
    ):
        project_folder_path: pathlib.Path = pathlib.Path(folder)

        stop_marker_path: pathlib.Path = project_folder_path / '.council' / 'stop'

        council: Council = Council(
            project_folder_path=project_folder_path,
        )

        async def loop() -> None:
            await council.connect(reset=reset)

            try:
                for step in range(steps):
                    if stop_marker_path.is_file():
                        logging.warning('stopped by the explicit file marker request')
                        break

                    logging.info('starting step %s/%s', step + 1, steps)
                    await council.step(step_idx=step, step_cnt=steps)


                logging.info('starting final step %s', steps)
                await council.step(step_idx=steps, step_cnt=steps)
            finally:
                await council.close()

        asyncio.run(loop())

    @staticmethod
    def load_yaml(path: pathlib.Path, yaml_loader_class: t.Type) -> t.Dict:
        with path.open('rt') as file:
            yaml_text = file.read()

        # noinspection PyTypeChecker
        yaml_dict = yaml.load(yaml_text, yaml_loader_class)

        return yaml_dict


if __name__ == '__main__':
    application = CouncilApplication()

    try:
        argh.dispatch_command(application.run)
    finally:
        logging.info('the work is finished')
        logging.shutdown()
