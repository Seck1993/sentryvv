import git
from flask import Flask, request

app = Flask(__name__)

@app.route('/update_server', methods=['POST'])
def webhook():
    if request.method == 'POST':
        repo = git.Repo('/home/valeverdepm/plataforma_policial')
        origin = repo.remotes.origin
        origin.pull()
        return 'Código atualizado com sucesso!', 200
    return 'Método não permitido', 405

if __name__ == "__main__":
    app.run()