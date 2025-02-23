import json
import asyncio
import git
from asgiref.sync import async_to_sync, sync_to_async
from asyncio import Queue

from channels.generic.websocket import AsyncWebsocketConsumer
from time import sleep
from FlapyTools import settings
import os
import shutil
import subprocess
from extractor.models import PyPiFlapyIndexLinks
from extractor.models import ALIndexLinks

from extractor.models import ALIndexLinks

diretorio_atual = os.path.dirname(__file__)

import csv


class CheckAlFlapyProcessHandler():
    stop_processing = False
    processing = False
    index_processor_websocket = None
    index_processor_websocket_queue = None

    @staticmethod
    async def compare_with_pypi_record(link):
        search_link = link.replace('https://', '')
        search_link = search_link.replace('http://', '')
        old_flapy_instance = await sync_to_async(PyPiFlapyIndexLinks.objects.filter)(url__icontains=search_link)
        old_flapy_instance_exists = await sync_to_async(old_flapy_instance.exists)()

        old_al_instance = await sync_to_async(ALIndexLinks.objects.filter)(url=link)
        old_al_instance_exists = await sync_to_async(old_al_instance.exists)()

        if old_al_instance_exists:
            if not old_flapy_instance_exists:
                return {'message': f"Awesome Python List record already registered, equivalent FlaPy url not found for {link}", 'level': 'error'}
            else:
                return {'message': f" Awesome Python List record ({link}) already registered , FlaPy url have been found in {old_flapy_instance.url} ", 'level': 'success'}
        else:
            new_al_link = await ALIndexLinks.objects.acreate(
                url=link,
            )

            if not old_flapy_instance_exists:
                return {'message': f"Awesome Python List record recorded, equivalent FlaPy url not found {link}", 'level': "warning"}
            else:
                old_flapy_instance = await sync_to_async(old_flapy_instance.first)()

                new_al_link.flapy_link = old_flapy_instance
                await sync_to_async(new_al_link.save)()
                return {'message': f" Awesome Python List record recorded, FlaPy url have been found {link}", 'level': 'success'}

    @staticmethod
    async def clone_project(url_repo, output_folder):
        try:
            await sync_to_async(os.mkdir)(output_folder)
            await sync_to_async(git.Repo.clone_from)(url_repo, output_folder)
            await sync_to_async(print)("Project cloned successfully!")
        except git.GitCommandError as e:
            await sync_to_async(print)(e)

    @staticmethod
    async def run_flapy(output_folder, flapy_dir, bash_file_dir, log_file, package_folder_dir, folder_name):
        try:
            os.chdir(flapy_dir,)
            await sync_to_async(print)("\n#######Running bash file")

            # comando_terminal = f"gnome-terminal -- bash -c '{bash_file_dir} >> {log_file} && rm -rf {package_folder_dir}; exit'"
            comando_terminal = f"touch {log_file} && " \
                               f"gnome-terminal -- bash -c '{bash_file_dir} >> {log_file} && rm -rf {package_folder_dir} && rm -rf results/example_results_{folder_name}; exit'"
            await sync_to_async(print)(comando_terminal)

            subprocess.run(comando_terminal, shell=True)
            # output = subprocess.run(["bash", bash_file_dir])

            with open(log_file, 'r') as output_file:
                saida_terminal = output_file.read()
            await sync_to_async(print)(saida_terminal)

        except Exception as e:
            await sync_to_async(print)(e)

    @staticmethod
    async def create_flapy_file(output_folder, package_folder_dir, package_name):
        try:

            output_folder_exists = await sync_to_async(os.path.exists)(output_folder)
            if output_folder_exists:
                await sync_to_async(os.remove)(output_folder)

            with open(output_folder, mode='w', newline='') as file:
                writer = csv.writer(file)
                writer.writerow(
                    ["PROJECT_NAME", "PROJECT_URL", "PROJECT_HASH", "PYPI_TAG", "FUNCS_TO_TRACE",
                     "TESTS_TO_RUN"])
                NUM_RUNS = 70
                writer.writerow([package_name, package_folder_dir, "", "", "",
                                 "", ])
            await sync_to_async(print)("Log file created successfully!")
        except git.GitCommandError as e:
            await sync_to_async(print)(e)

    @staticmethod
    async def create_bash_file(bash_file_dir, output_folder, folder_name, flapy_dir):
        try:
            bash_command = f" time ./flapy.sh run --out-dir ./results/example_results_{folder_name} {output_folder} 1  && " \
                           f" time ./flapy.sh parse ResultsDirCollection --path ./results/example_results_{folder_name} get_tests_overview _df to_csv --index=false"

            bash_file_dir_exists = await sync_to_async(os.path.exists)(bash_file_dir)
            if bash_file_dir_exists:
                await sync_to_async(os.remove)(bash_file_dir)

            with open(bash_file_dir, "w") as bash_file:
                bash_file.write(bash_command)

            os.chmod(bash_file_dir, 0o755)
            await sync_to_async(print)("Bash file created successfully!")
        except Exception as e:
            await sync_to_async(print)(e)

    @staticmethod
    async def start_processing(queue):
        await sync_to_async(print)("Start processing")
        CheckAlFlapyProcessHandler.index_processor_websocket_queue = queue
        flapy_github_url = "https://github.com/gabrielmtararam/FlaPy-custom"
        base_dir = await sync_to_async(str)(settings.BASE_DIR)
        flapy_dir = base_dir + "/repositories/flapy"
        rep_dir = base_dir + "/repositories/"

        max_packages = 500

        rep_dir_exists = await sync_to_async(os.path.exists)(rep_dir)
        if not rep_dir_exists:
            await sync_to_async(os.mkdir)(rep_dir)


        flapy_folder_exists = await sync_to_async(os.path.exists)(flapy_dir)
        if not flapy_folder_exists:
            await CheckAlFlapyProcessHandler.clone_project(flapy_github_url, flapy_dir)

        if not CheckAlFlapyProcessHandler.processing:

            bash_file_dir = flapy_dir+"/run_custom_flapy.sh"
            output_folder = flapy_dir + "/temporary_example.csv"
            log_folder = flapy_dir + "/log"

            log_folder_exists = await sync_to_async(os.path.exists)(log_folder)
            if not log_folder_exists:
                await sync_to_async(os.mkdir)(log_folder)


            al_query = {
                "flapy_link": None,
                "processed_by_flapy": False,
            }
            al_filtered = await sync_to_async(ALIndexLinks.objects.filter)(**al_query)
            qtd_pacotes = await sync_to_async(al_filtered.count)()
            await sync_to_async(print)(f"Filtered project count: {qtd_pacotes}")
            await sync_to_async(print)(f"Base dir: {base_dir}")

            count = 0
            al_filtered = await sync_to_async(list)(al_filtered)
            for package in al_filtered:
                count += 1
                folder_name = package.url.replace('/', '').replace('-', '').replace('.', '').replace(':', '')
                package_folder_dir = rep_dir + folder_name + ""

                log_file = flapy_dir + "/log/"+folder_name+".txt"
                await CheckAlFlapyProcessHandler.create_bash_file(bash_file_dir, output_folder, folder_name, flapy_dir)

                print_value = f"Running project {package.url} on  {package_folder_dir}"
                await sync_to_async(print)(print_value)

                package_folder_dirr_exists = await sync_to_async(os.path.exists)(package_folder_dir)
                if package_folder_dirr_exists:
                    await sync_to_async(shutil.rmtree)(package_folder_dir)

                await CheckAlFlapyProcessHandler.clone_project(package.url, package_folder_dir + "/")

                await CheckAlFlapyProcessHandler.create_flapy_file(output_folder, package_folder_dir, folder_name)

                await CheckAlFlapyProcessHandler.run_flapy(output_folder, flapy_dir, bash_file_dir, log_file, package_folder_dir, folder_name)
                package.processed_by_flapy = True
                await sync_to_async(package.save)()
                await sync_to_async(print)(count)
                if count >= max_packages:
                    break
                sleep(30)
            await sync_to_async(print)("Finished processing")

            await queue.put({'message': f"All links recorded sucessefuly ", 'level': 'error'})
            return


class CheckAlFlapyProcess(AsyncWebsocketConsumer):
    async def connect(self):
        self.queue = Queue()
        self.stop_processing = False

        await self.accept()
        await self.send(text_data=json.dumps({
            'type': 'feedback_message_value',
            'message': "started_socket_sucessefuly"
        }))

    async def process_messages(self):
        asyncio.create_task(CheckAlFlapyProcessHandler.start_processing(self.queue))
        while True:
            message = await self.queue.get()
            await self.send_feedback_message_level(message)

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message = text_data_json['message']
        if message == "start_processing_al":
            asyncio.create_task(self.process_messages())
        elif message == "stop_processing_al":
            CheckAlFlapyProcessHandler.stop_processing = True

    async def send_feedback_message(self, message):
        await self.send(text_data=json.dumps({
            'type': 'success',
            'message': message
        }))

    async def send_feedback_message_level(self, message):
        # print("message ",message)
        await self.send(text_data=json.dumps({
            'type': message['level'],
            'message': message['message']
        }))
