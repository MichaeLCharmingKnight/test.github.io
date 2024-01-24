import time
import re
import uuid
from flask import Flask, render_template, request, jsonify, make_response, redirect, url_for
from threading import Thread
from openai import OpenAI
from datetime import datetime
from flask_cors import CORS

app = Flask(__name__, static_folder='static', template_folder='templates')

CORS(app)

processed_messages = []
processed_user_messages = []
processed_assistant_messages = []
submit_enabled = True
all_messages = []
all_messages_history = []

def read_api_key_from_file(file_path):
    try:
        with open(file_path, 'r') as file:
            api_key = file.read().strip()
            return api_key
    except FileNotFoundError:
        print(f"Erro: Arquivo não encontrado - {file_path}")
        return None


def create_assistant():
    global client, my_assistant, instructions
    instructions = """
        Bem-vindo ao Meu Pet Club! Estou aqui para ajudar com informações relacionadas a cachorros, gatos e detalhes do plano de venda fornecidos nos documentos.

        1. Ao responder perguntas, dê prioridade a informações presentes no documento fornecido.

        2. Enfatize respostas relacionadas a cachorros, gatos e, principalmente, aos planos de venda descritos nos documentos.

        3. Utilize o documento "Roteiro.txt" no arquivo "file" como guia para auxiliar nas perguntas e respostas, adaptando-se conforme necessário.

        4. **As informações detalhadas sobre os planos (Plano De Boa, Plano Básico, Plano Plus, Plano Total e Plano Top) estão no documento "Plano oferecido pela empresa Meu Pet Club" no arquivo "file1".** Este documento contém serviços/coberturas oferecidos, detalhes de reembolso por evento e os valores associados a cada plano.

        5. Consulte o documento "Condições Gerais" no arquivo "file2" para orientação sobre as práticas e normas relacionadas aos planos oferecidos. Este documento inclui regras de negócio, o que é permitido ou não nos planos, e cláusulas contratuais que definem coberturas, exclusões gerais, direitos e obrigações das partes.

        6. Se a pergunta não estiver relacionada a cachorros, gatos ou aos planos de venda da empresa, responda educadamente que a pergunta está fora do escopo atual.

        Lembre-se de manter respostas claras e informativas para proporcionar uma ótima experiência aos usuários do Meu Pet Club!
    """

    api_key = read_api_key_from_file("/home/michael/Downloads/GPT1/GPT/api_keys.txt")
    if not api_key:
        print("Erro: Chave de API não encontrada.")
        return None, None

    client = OpenAI(api_key=api_key)

    file = client.files.create(
        file=open("/home/michael/Downloads/GPT1/GPT/Roteiro", "rb"),
        purpose='assistants'
    )
    instructions
    file1 = client.files.create(
        file=open("/home/michael/Downloads/GPT1/GPT/Plano", "rb"),
        purpose='assistants'
    )

    file2 = client.files.create(
        file=open("/home/michael/Downloads/GPT1/GPT/Condição_gerais", "rb"),
        purpose='assistants'
    )

    my_assistant = client.beta.assistants.create(
        instructions=instructions,
        name="MPC",
        tools=[{"type": "retrieval"}],
        model="gpt-4-1106-preview",
        file_ids=[file.id, file1.id, file2.id],
    )

    print(my_assistant)

    return client, my_assistant, instructions



create_assistant()

empty_thread = client.beta.threads.create()




def sort_messages(processed_messages):
    messages = sorted(processed_messages, key=lambda x: x[0])
    return messages


def save_to_file(messages, filename):
    with open(filename, 'w') as arquivo:
        for timestamp, role, content in messages:
            arquivo.write(f"{timestamp.strftime('%d/%m/%Y %H:%M:%S')} {role}: {content}\n")


def run_chat(user_input, user_key):
    global submit_enabled, all_messages, all_messages_history
    empty_thread = client.beta.threads.create()

    submit_enabled = False
    timestamp = datetime.now()
    formatted_timestamp = timestamp.strftime('%d/%m/%Y %H:%M:%S')

    role_user = 'Usuário'
    content_user = user_input

    processed_user_messages.append((timestamp, role_user, content_user))
    all_messages.append((timestamp, role_user, content_user))

    if user_input.lower() == 'sair':
        processed_messages = sort_messages(processed_user_messages + processed_assistant_messages)
        nome_arquivo = f"/home/michael/Downloads/GPT1/GPT/data/{processed_messages[0][0].strftime('%Y_%m_%d_%H%M%S')}_historico_conversa.txt"
        save_to_file(processed_messages, nome_arquivo)
        submit_enabled = False
        all_messages_history.extend(all_messages)
        return "Conversa encerrada.", all_messages

    thread_message = client.beta.threads.messages.create(
        thread_id=empty_thread.id,
        role="user",
        content=user_input
    )

    run = client.beta.threads.runs.create(
        thread_id=empty_thread.id,
        assistant_id=my_assistant.id,
        instructions=instructions,
    )

    assistant_messages = []

    while True:
        run = client.beta.threads.runs.retrieve(
            thread_id=empty_thread.id,
            run_id=run.id
        )

        messages = client.beta.threads.messages.list(
            thread_id=empty_thread.id,
            limit="50"
        )
        print(messages)

        if run.status == 'completed':
            for message in messages.data:
                if message.content and message.content[0].text.value not in processed_assistant_messages:
                    role = message.role.capitalize()
                    content = message.content[0].text.value
                    content = re.sub(r'【.*?】', '', content)
                    content = content.replace('&#8203;', '').replace('``', '').replace('†source', '')

                    if role.lower() == 'user':
                        processed_user_messages.append((timestamp, role_user, content))
                        all_messages.append((timestamp, role_user, content))
                    else:
                        processed_assistant_messages.append((timestamp, role, content))
                        all_messages.append((timestamp, role, content))

                    # Include the assistant's response in the list to return
                    assistant_messages.append((timestamp, role, content))

                    break

            processed_messages = sort_messages(processed_user_messages + processed_assistant_messages)
            nome_arquivo = f"/home/michael/Downloads/GPT1/GPT/data/{processed_messages[0][0].strftime('%Y_%m_%d_%H%M%S')}_historico_conversa.txt"
            save_to_file(processed_messages, nome_arquivo)
            submit_enabled = True
            break

    return assistant_messages


TIMEOUT_IN_SECONDS = 60
last_activity_time = time.time()
LAST_ACTIVITY_KEY = 'last_activity_time'


@app.route('/', methods=['GET', 'POST'])
def index():
    global submit_enabled, last_activity_time, all_messages
    user_key = request.cookies.get('user_key', str(uuid.uuid4()))
    if request.method == 'POST':
        user_input = request.form.get('user_input')
        user_key = request.form.get('user_key')
        assistant_messages = run_chat(user_input, user_key)
        response = make_response(render_template(user_input=user_input, assistant_messages=assistant_messages, all_messages=all_messages, submit_enabled=submit_enabled, run_chat=run_chat))
        last_activity_time = time.time()
        response.set_cookie(LAST_ACTIVITY_KEY, str(last_activity_time))
        response.set_cookie('user_key', user_key)
        return response
    current_time = time.time()
    last_activity_time = float(request.cookies.get(LAST_ACTIVITY_KEY, 0))
    if current_time - last_activity_time > TIMEOUT_IN_SECONDS:
        restart_chat()
    redirect_warning = request.args.get('redirect_warning', False)
    return render_template('index.html', submit_enabled=submit_enabled, all_messages=all_messages, redirect_warning=redirect_warning)

@app.route('/submit', methods=['POST'])
def submit():
    global last_activity_time, all_messages_history
    last_activity_time = time.time()
    user_input = request.form.get('user_input')
    assistant_messages = run_chat(user_input)

    for message in all_messages:
        role = message[1]
        content = message[2]
        image_path = f'/static/teste1.png' if role == 'Usuário' else f'/static/teste.png'
        all_messages_history.append([message[0].strftime('%d/%m/%Y %H:%M:%S'), role, content, image_path])

    messages_html = ""

    for message in all_messages_history:
        timestamp = message[0]
        role = message[1]
        content = message[2]
        image_path = message[3]

        messages_html += f"""
            <div class="{role.lower()}-response">
                <div class="message-content">
                    <img src="{image_path}" alt="Imagem de {role}" class="{role.lower()}-image" style="width: 25px; height: 25px;">
                    <p><strong>{role}</strong><br>{content}</p>
                </div>
            </div>
        """

    return jsonify({'messages_html': messages_html})


def restart_chat():
    global submit_enabled, processed_user_messages, all_messages, last_activity_time
    submit_enabled = True
    processed_user_messages.clear()
    last_activity_time = time.time()

@app.route('/chat', methods=['GET'])
def chat():
    return render_template('index.html')

@app.route('/history', methods=['GET'])
def get_history():
    global all_messages_history
    return jsonify({'messages_html': all_messages_history})

@app.route('/get_response', methods=['POST'])
def get_response():
    user_input = request.form.get('user_input')
    user_key = request.form.get('user_key')
    assistant_messages = run_chat(user_input, user_key)
    return jsonify({'assistant_messages': assistant_messages})


if __name__ == '__main__':
    app.run(debug=True)