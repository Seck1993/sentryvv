from flask import Flask, render_template, request, redirect, session, url_for, send_from_directory
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from PIL import Image
import os
from datetime import timedelta
from sqlalchemy import text
import base64
import uuid
import time  # Importação necessária para o Cache Busting
from io import BytesIO # Necessário para o processamento de imagem em memória

app = Flask(__name__)
app.secret_key = "seguranca_sargento_valeverde_sentry_v3"
app.permanent_session_lifetime = timedelta(days=30)

# Caminhos PythonAnywhere
base_dir = "/home/valeverdepm/plataforma_policial"
upload_folder = os.path.join(base_dir, 'static/uploads')
if not os.path.exists(upload_folder):
    os.makedirs(upload_folder)

app.config['UPLOAD_FOLDER'] = upload_folder
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(base_dir, 'database_v3.db')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# --- MODELAGEM ---

class Usuario(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(50), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)

class TokenCadastro(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(20), unique=True, nullable=False)
    usado = db.Column(db.Boolean, default=False)

class Pessoa(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    nome_completo = db.Column(db.String(100), nullable=False)
    apelido = db.Column(db.String(50))
    nascimento = db.Column(db.String(20))
    documento = db.Column(db.String(20))
    endereco = db.Column(db.String(200))
    lat = db.Column(db.Float, default=-29.7562)
    lng = db.Column(db.Float, default=-52.1458)
    foto_path = db.Column(db.String(200), default="/static/logo.png")
    modus_operandi = db.Column(db.Text)
    embolamento = db.Column(db.String(50))
    veiculos = db.relationship('Veiculo', backref='condutor', lazy=True)

class Veiculo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    placa = db.Column(db.String(10), unique=True, nullable=False)
    tipo = db.Column(db.String(20)) 
    marca_modelo = db.Column(db.String(100))
    cor = db.Column(db.String(30))
    obs = db.Column(db.Text)
    foto_path = db.Column(db.String(200), default="/static/car_default.png") # Nova Coluna
    pessoa_id = db.Column(db.Integer, db.ForeignKey('pessoa.id'), nullable=True)

class Vinculo(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pessoa_origem_id = db.Column(db.Integer, db.ForeignKey('pessoa.id'))
    pessoa_destino_id = db.Column(db.Integer, db.ForeignKey('pessoa.id'))
    tipo_vinculo = db.Column(db.String(50))
    origem = db.relationship('Pessoa', foreign_keys=[pessoa_origem_id])
    destino = db.relationship('Pessoa', foreign_keys=[pessoa_destino_id])

with app.app_context():
    db.create_all()
    if not Usuario.query.filter_by(username='admin').first():
        admin = Usuario(username='admin', password=generate_password_hash('admin123'), is_admin=True)
        db.session.add(admin)
        db.session.commit()

# --- ROTA DE MIGRAÇÃO ATUALIZADA ---
@app.route('/migrar')
def migrar():
    try:
        with db.engine.connect() as conn:
            # Tenta adicionar novas colunas se não existirem
            try: conn.execute(text("ALTER TABLE pessoa ADD COLUMN modus_operandi TEXT"))
            except: pass
            try: conn.execute(text("ALTER TABLE pessoa ADD COLUMN embolamento VARCHAR(50)"))
            except: pass
            try: conn.execute(text("ALTER TABLE veiculo ADD COLUMN foto_path VARCHAR(200) DEFAULT '/static/car_default.png'"))
            except: pass
            conn.commit()
        return "Migração tática concluída! Sistema de fotos para veículos ativado."
    except Exception as e:
        return f"Erro na migração: {str(e)}"

# --- AUXILIARES ---

def processar_foto_base64(foto_data):
    try:
        if not foto_data or ';base64,' not in foto_data: return None
        format, imgstr = foto_data.split(';base64,') 
        img_data = base64.b64decode(imgstr)
        filename = f"alvo_{uuid.uuid4().hex}.jpg"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        img = Image.open(BytesIO(img_data))
        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
        img = img.resize((500, 500), Image.LANCZOS)
        img.save(filepath, "JPEG", optimize=True, quality=85)
        return '/static/uploads/' + filename
    except Exception as e:
        print(f"Erro imagem pessoa: {e}")
        return None

# NOVO: Processamento específico para Veículos (Widescreen 16:9)
def processar_foto_veiculo_base64(foto_data):
    try:
        if not foto_data or ';base64,' not in foto_data: return None
        format, imgstr = foto_data.split(';base64,') 
        img_data = base64.b64decode(imgstr)
        filename = f"veiculo_{uuid.uuid4().hex}.jpg"
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        img = Image.open(BytesIO(img_data))
        if img.mode in ("RGBA", "P"): img = img.convert("RGB")
        # REDIMENSIONAMENTO FÍSICO 16:9 (800x450)
        img = img.resize((800, 450), Image.LANCZOS)
        img.save(filepath, "JPEG", optimize=True, quality=85)
        return '/static/uploads/' + filename
    except Exception as e:
        print(f"Erro imagem veiculo: {e}")
        return None

def processar_foto(file):
    filename = secure_filename(file.filename)
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    img = Image.open(file)
    if img.mode in ("RGBA", "P"): img = img.convert("RGB")
    img.thumbnail((800, 800))
    img.save(filepath, "JPEG", optimize=True, quality=70)
    return '/static/uploads/' + filename

# --- ROTAS PRINCIPAIS ---

@app.route('/')
def index():
    if 'user_id' not in session: return redirect(url_for('login'))
    pessoas = Pessoa.query.order_by(Pessoa.id.desc()).limit(10).all()
    veiculos = Veiculo.query.order_by(Veiculo.id.desc()).limit(10).all()
    return render_template('index.html', pessoas=pessoas, veiculos=veiculos, ts=int(time.time()))

@app.route('/lista_geral')
def lista_geral():
    if 'user_id' not in session: return redirect(url_for('login'))
    pessoas = Pessoa.query.order_by(Pessoa.nome_completo).all()
    veiculos = Veiculo.query.order_by(Veiculo.placa).all()
    return render_template('lista_geral.html', pessoas=pessoas, veiculos=veiculos, ts=int(time.time()))

@app.route('/visualizar_pessoa/<int:id>')
def visualizar_pessoa(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    p = Pessoa.query.get_or_404(id)
    return render_template('visualizar_pessoa.html', p=p, ts=int(time.time()))

# NOVO: Rota para visualizar a ficha do veículo
@app.route('/visualizar_veiculo/<int:id>')
def visualizar_veiculo(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    v = Veiculo.query.get_or_404(id)
    return render_template('visualizar_veiculo.html', v=v, ts=int(time.time()))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        user = Usuario.query.filter_by(username=request.form.get('username')).first()
        if user and check_password_hash(user.password, request.form.get('password')):
            session.permanent = True
            session['user_id'] = user.id
            session['username'] = user.username
            session['is_admin'] = user.is_admin
            return redirect(url_for('index'))
    return render_template('login.html')

# --- ROTAS DE PESSOA ---

@app.route('/registrar')
def registrar():
    if 'user_id' not in session: return redirect(url_for('login'))
    pessoas_existentes = Pessoa.query.order_by(Pessoa.nome_completo).all()
    return render_template('cadastro.html', pessoas_existentes=pessoas_existentes)

@app.route('/cadastrar', methods=['POST'])
def cadastrar():
    if 'user_id' not in session: return redirect(url_for('login'))
    foto_url = "/static/logo.png"
    foto_editada = request.form.get('foto_editada')
    if foto_editada:
        nova_url = processar_foto_base64(foto_editada)
        if nova_url: foto_url = nova_url
    elif 'foto' in request.files:
        file = request.files['foto']
        if file.filename != '': foto_url = processar_foto(file)
    
    nova = Pessoa(
        nome_completo=request.form.get('nome'), 
        apelido=request.form.get('apelido'), 
        nascimento=request.form.get('nascimento'), 
        documento=request.form.get('documento'),
        endereco=request.form.get('endereco'), 
        lat=float(request.form.get('lat', -29.7562)),
        lng=float(request.form.get('lng', -52.1458)), 
        foto_path=foto_url,
        modus_operandi=request.form.get('modus_operandi'),
        embolamento=request.form.get('embolamento')
    )
    db.session.add(nova)
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/editar_pessoa/<int:id>')
def editar_pessoa(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    p = Pessoa.query.get_or_404(id)
    return render_template('editar_pessoa.html', p=p)

@app.route('/atualizar_pessoa/<int:id>', methods=['POST'])
def atualizar_pessoa(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    p = Pessoa.query.get_or_404(id)
    p.nome_completo = request.form.get('nome')
    p.apelido = request.form.get('apelido')
    p.documento = request.form.get('documento')
    p.embolamento = request.form.get('embolamento')
    p.modus_operandi = request.form.get('modus_operandi')
    p.lat = float(request.form.get('lat'))
    p.lng = float(request.form.get('lng'))
    
    foto_editada = request.form.get('foto_editada')
    if foto_editada:
        nova_url = processar_foto_base64(foto_editada)
        if nova_url: p.foto_path = nova_url
    elif 'foto' in request.files:
        file = request.files['foto']
        if file.filename != '': p.foto_path = processar_foto(file)
            
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/excluir_pessoa/<int:id>')
def excluir_pessoa(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    p = Pessoa.query.get_or_404(id)
    Vinculo.query.filter((Vinculo.pessoa_origem_id == id) | (Vinculo.pessoa_destino_id == id)).delete()
    db.session.delete(p)
    db.session.commit()
    return redirect(url_for('index'))

# --- ROTAS DE VÍNCULOS ---

@app.route('/vincular_tela')
def vincular_tela():
    if 'user_id' not in session: return redirect(url_for('login'))
    pessoas = Pessoa.query.order_by(Pessoa.nome_completo).all()
    vinculos_existentes = Vinculo.query.all()
    return render_template('vincular_geral.html', pessoas=pessoas, vinculos=vinculos_existentes)

@app.route('/salvar_vinculo', methods=['POST'])
def salvar_vinculo():
    if 'user_id' not in session: return redirect(url_for('login'))
    p1 = request.form.get('origem')
    p2 = request.form.get('destino')
    tipo = request.form.get('relacao') or "Vínculo"
    if p1 and p2 and p1 != p2:
        novo_v = Vinculo(pessoa_origem_id=p1, pessoa_destino_id=p2, tipo_vinculo=tipo)
        db.session.add(novo_v)
        db.session.commit()
    return redirect(url_for('vincular_tela'))

@app.route('/excluir_vinculo/<int:id>')
def excluir_vinculo(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    v = Vinculo.query.get_or_404(id)
    db.session.delete(v)
    db.session.commit()
    return redirect(url_for('vincular_tela'))

# --- ROTAS DE VEÍCULO ---

@app.route('/cadastrar_veiculo', methods=['GET', 'POST'])
def cadastrar_veiculo():
    if 'user_id' not in session: return redirect(url_for('login'))
    if request.method == 'POST':
        foto_url = "/static/car_default.png"
        foto_editada = request.form.get('foto_editada')
        if foto_editada:
            nova_url = processar_foto_veiculo_base64(foto_editada)
            if nova_url: foto_url = nova_url
            
        novo_v = Veiculo(
            placa=request.form.get('placa').upper().replace("-", "").replace(" ", ""),
            tipo=request.form.get('tipo'),
            marca_modelo=request.form.get('marca_modelo'),
            cor=request.form.get('cor'),
            obs=request.form.get('obs'),
            foto_path=foto_url, # Grava Foto
            pessoa_id=request.form.get('pessoa_id') or None
        )
        db.session.add(novo_v)
        db.session.commit()
        return redirect(url_for('index'))
    pessoas = Pessoa.query.order_by(Pessoa.nome_completo).all()
    return render_template('cadastro_veiculo.html', pessoas=pessoas)

@app.route('/editar_veiculo/<int:id>')
def editar_veiculo(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    v = Veiculo.query.get_or_404(id)
    pessoas = Pessoa.query.order_by(Pessoa.nome_completo).all()
    return render_template('editar_veiculo.html', v=v, pessoas=pessoas)

@app.route('/atualizar_veiculo/<int:id>', methods=['POST'])
def atualizar_veiculo(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    v = Veiculo.query.get_or_404(id)
    v.placa = request.form.get('placa').upper().replace("-", "").replace(" ", "")
    v.tipo = request.form.get('tipo')
    v.marca_modelo = request.form.get('marca_modelo')
    v.cor = request.form.get('cor')
    v.obs = request.form.get('obs')
    v.pessoa_id = request.form.get('pessoa_id') or None
    
    # Processa Foto do Veículo
    foto_editada = request.form.get('foto_editada')
    if foto_editada:
        nova_url = processar_foto_veiculo_base64(foto_editada)
        if nova_url: v.foto_path = nova_url
        
    db.session.commit()
    return redirect(url_for('index'))

@app.route('/excluir_veiculo/<int:id>')
def excluir_veiculo(id):
    if 'user_id' not in session: return redirect(url_for('login'))
    v = Veiculo.query.get_or_404(id)
    db.session.delete(v)
    db.session.commit()
    return redirect(url_for('index'))

# --- ROTAS ADMINISTRATIVAS ---

@app.route('/admin/tokens', methods=['GET', 'POST'])
def gerenciar_tokens():
    if not session.get('is_admin'): return redirect(url_for('index'))
    if request.method == 'POST':
        novo_codigo = request.form.get('novo_codigo')
        if novo_codigo:
            db.session.add(TokenCadastro(codigo=novo_codigo))
            db.session.commit()
    tokens = TokenCadastro.query.all()
    usuarios = Usuario.query.all()
    return render_template('admin_tokens.html', tokens=tokens, usuarios=usuarios)

@app.route('/excluir_token/<int:id>')
def excluir_token(id):
    if not session.get('is_admin'): return redirect(url_for('index'))
    t = TokenCadastro.query.get_or_404(id)
    db.session.delete(t)
    db.session.commit()
    return redirect(url_for('gerenciar_tokens'))

@app.route('/excluir_usuario/<int:id>')
def excluir_usuario(id):
    if not session.get('is_admin'): return redirect(url_for('index'))
    u = Usuario.query.get_or_404(id)
    if u.username != 'admin':
        db.session.delete(u)
        db.session.commit()
    return redirect(url_for('gerenciar_tokens'))

@app.route('/novo_usuario', methods=['GET', 'POST'])
def novo_usuario():
    if request.method == 'POST':
        codigo = request.form.get('token')
        token = TokenCadastro.query.filter_by(codigo=codigo, usado=False).first()
        if token:
            user = Usuario(
                username=request.form.get('username'),
                password=generate_password_hash(request.form.get('password')),
                is_admin=False
            )
            token.usado = True
            db.session.add(user)
            db.session.commit()
            return redirect(url_for('login'))
        return "Sequência/Token Inválido ou já usado!"
    return render_template('registrar.html')

# --- ROTAS DE INTELIGÊNCIA (ÁRVORE) ---

@app.route('/visualizar_arvore')
@app.route('/visualizar_arvore/<int:pessoa_id>')
def visualizar_arvore(pessoa_id=None):
    if 'user_id' not in session: return redirect(url_for('login'))
    pessoas_lista = Pessoa.query.order_by(Pessoa.nome_completo).all()
    nodes = []
    edges = []
    alvo_central = None
    if pessoa_id:
        alvo_central = Pessoa.query.get(pessoa_id)
        vinculos = Vinculo.query.filter((Vinculo.pessoa_origem_id == pessoa_id) | (Vinculo.pessoa_destino_id == pessoa_id)).all()
        nodes.append({"id": alvo_central.id, "label": alvo_central.nome_completo, "shape": "circularImage", "image": alvo_central.foto_path + f"?v={int(time.time())}", "size": 45, "borderWidth": 6, "color": {"border": "#d9534f", "background": "#ffffff"}})
        for v in vinculos:
            conexao = v.destino if v.pessoa_origem_id == pessoa_id else v.origem
            if not any(n['id'] == conexao.id for n in nodes):
                nodes.append({"id": conexao.id, "label": f"{conexao.nome_completo}\n({conexao.apelido or 'S/V'})", "shape": "circularImage", "image": conexao.foto_path + f"?v={int(time.time())}", "size": 30, "borderWidth": 3, "color": {"border": "#1a3a5f"}})
            edges.append({"from": v.pessoa_origem_id, "to": v.pessoa_destino_id, "label": v.tipo_vinculo.upper(), "font": {"size": 10, "color": "#d9534f", "strokeWidth": 2, "strokeColor": "#ffffff"}, "arrows": {"to": {"enabled": True, "scaleFactor": 0.5}}, "color": {"color": "#1a3a5f", "opacity": 0.6}})
    return render_template('arvore.html', nodes=nodes, edges=edges, pessoas_lista=pessoas_lista, alvo_central=alvo_central)

# --- OUTRAS ROTAS ---

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route('/mapa')
def mapa_tela():
    if 'user_id' not in session: return redirect(url_for('login'))
    return render_template('mapa.html', pessoas=Pessoa.query.all())

@app.route('/manifest.json')
def manifest():
    return send_from_directory('static', 'manifest.json')

if __name__ == '__main__':
    app.run(debug=True)