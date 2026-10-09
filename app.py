import hashlib
import sqlite3
from datetime import date, datetime
from dateutil.relativedelta import relativedelta
import pandas as pd
import streamlit as st

DB_NAME = "financas.db"


# --- Funções de Segurança e Base de Dados ---
def hash_password(password: str) -> str:
  return hashlib.sha256(password.encode("utf-8")).hexdigest()


def get_db():
  conn = sqlite3.connect(DB_NAME, timeout=30.0)
  conn.row_factory = sqlite3.Row
  conn.execute("PRAGMA journal_mode=WAL;")
  return conn


def init_db():
  with get_db() as conn:
    c = conn.cursor()
    # 1. Usuários
    c.execute("""
            CREATE TABLE IF NOT EXISTS usuarios (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                nome TEXT NOT NULL,
                email TEXT,
                celular TEXT,
                password_hash TEXT NOT NULL
            )
        """)

    for col, tipocol in [("email", "TEXT"), ("celular", "TEXT")]:
      try:
        c.execute(f"ALTER TABLE usuarios ADD COLUMN {col} {tipocol}")
      except sqlite3.OperationalError:
        pass

    # 2. Transações
    c.execute("""
            CREATE TABLE IF NOT EXISTS transacoes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                data TEXT NOT NULL,
                descricao TEXT NOT NULL,
                tipo TEXT NOT NULL,
                categoria TEXT NOT NULL,
                metodo TEXT NOT NULL,
                ciclo TEXT DEFAULT 'Outro',
                valor REAL NOT NULL,
                mes_fatura TEXT,
                parcela_atual INTEGER DEFAULT 1,
                total_parcelas INTEGER DEFAULT 1
            )
        """)

    colunas_extras = [
        ("usuario_id", "INTEGER DEFAULT 1"),
        ("metodo", "TEXT NOT NULL DEFAULT 'Pix'"),
        ("ciclo", "TEXT DEFAULT 'Outro'"),
        ("mes_fatura", "TEXT"),
        ("parcela_atual", "INTEGER DEFAULT 1"),
        ("total_parcelas", "INTEGER DEFAULT 1"),
    ]
    for col, tipocol in colunas_extras:
      try:
        c.execute(f"ALTER TABLE transacoes ADD COLUMN {col} {tipocol}")
      except sqlite3.OperationalError:
        pass

    # 3. Financiamentos e Contratos Fixos
    c.execute("""
            CREATE TABLE IF NOT EXISTS parcelamentos (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                usuario_id INTEGER NOT NULL,
                titulo TEXT NOT NULL,
                tipo_contrato TEXT NOT NULL,
                total_parcelas INTEGER NOT NULL,
                parcelas_pagas INTEGER NOT NULL DEFAULT 0,
                valor_parcela REAL NOT NULL,
                dia_vencimento INTEGER NOT NULL
            )
        """)
    conn.commit()


init_db()

# --- Configuração Visual Global ---
st.set_page_config(
    page_title="Apex Finance | Controle Pessoal",
    layout="wide",
    page_icon="💳",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .stApp {
            background-color: #0b0f19;
            color: #f1f5f9;
        }
        
        .block-container { 
            padding-top: 4.5rem !important; 
            padding-bottom: 3rem !important; 
        }

        button[data-baseweb="tab"] {
            font-size: 1.05rem !important;
            padding: 10px 22px !important;
            font-weight: 600 !important;
        }

        .login-box {
            background: linear-gradient(160deg, rgba(26, 34, 53, 0.85), rgba(15, 23, 42, 0.98));
            backdrop-filter: blur(14px);
            -webkit-backdrop-filter: blur(14px);
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 22px;
            padding: 40px 32px;
            box-shadow: 0 20px 40px rgba(0, 0, 0, 0.5), 0 0 25px rgba(56, 189, 248, 0.08);
            margin-top: 1rem;
            margin-bottom: 1.5rem;
        }

        .login-header {
            text-align: center;
            margin-bottom: 24px;
        }

        .login-title {
            font-size: 2.2rem;
            font-weight: 800;
            letter-spacing: -0.5px;
            background: linear-gradient(90deg, #38bdf8, #818cf8);
            -webkit-background-clip: text;
            -webkit-text-fill-color: transparent;
            margin-bottom: 4px;
        }

        .login-subtitle {
            color: #94a3b8;
            font-size: 0.92rem;
        }

        .stMetric {
            background-color: #1e293b !important;
            border: 1px solid #334155 !important;
            border-radius: 12px !important;
            padding: 16px !important;
        }

        .card-ciclo {
            background: #1e293b;
            padding: 18px;
            border-radius: 10px;
            border-left: 5px solid #38bdf8;
            margin-bottom: 14px;
        }
    </style>
""",
    unsafe_allow_html=True,
)

# Sessão
if "user_id" not in st.session_state:
  st.session_state["user_id"] = None
if "user_nome" not in st.session_state:
  st.session_state["user_nome"] = None


# --- Modal de Recuperação de Senha ---
@st.dialog("🔑 Recuperação de Acesso")
def modal_recuperar_senha():
  st.caption(
      "Informe o seu usuário e o e-mail ou celular cadastrado para validar sua"
      " identidade."
  )
  r_user = st.text_input(
      "Usuário", key="rec_u", placeholder="Digite seu usuário"
  ).lower()
  r_contato = st.text_input(
      "E-mail ou Celular cadastrado",
      key="rec_cont",
      placeholder="exemplo@email.com ou 11999998888",
  ).lower()
  r_new_pass = st.text_input(
      "Nova Senha",
      type="password",
      key="rec_np",
      placeholder="Mínimo 4 caracteres",
  )

  st.write("")
  if st.button("Salvar Nova Senha", type="primary", use_container_width=True):
    if r_user.strip() and r_contato.strip() and r_new_pass.strip():
      if len(r_new_pass.strip()) < 4:
        st.error("A nova senha deve ter no mínimo 4 caracteres.")
      else:
        with get_db() as conn:
          c = conn.cursor()
          c.execute(
              """
                        SELECT id FROM usuarios 
                        WHERE lower(username) = ? AND (lower(email) = ? OR celular = ?)
                    """,
              (r_user.strip().lower(), r_contato.strip(), r_contato.strip()),
          )
          encontrado = c.fetchone()
          if encontrado:
            c.execute(
                "UPDATE usuarios SET password_hash = ? WHERE id = ?",
                (hash_password(r_new_pass.strip()), encontrado["id"]),
            )
            conn.commit()
            st.success(
                "🎉 Senha alterada com sucesso! Você já pode fechar esta janela"
                " e entrar."
            )
          else:
            st.error("Dados informados não conferem com o cadastro.")
    else:
      st.warning("Preencha todos os campos para recuperar a senha.")


# --- Tela de Autenticação ---
def tela_autenticacao():
  _, col_centro, _ = st.columns([1, 1.4, 1])

  with col_centro:
    st.markdown(
        """
        <div class="login-box">
            <div class="login-header">
                <div class="login-title">💼 Apex Finance</div>
                <div class="login-subtitle">Gestão Financeira & Controle Inteligente</div>
            </div>
        """,
        unsafe_allow_html=True,
    )

    tab_log, tab_cad = st.tabs(["🔐 Acessar", "📝 Criar Conta"])

    with tab_log:
      st.write("")
      u_log = st.text_input(
          "Nome de Usuário", key="txt_login_u", placeholder="Digite seu usuário"
      )
      p_log = st.text_input(
          "Senha",
          type="password",
          key="txt_login_p",
          placeholder="Digite sua senha",
      )

      col_esq, col_dir = st.columns([1, 1.3])
      with col_dir:
        st.markdown(
            "<div style='text-align: right; padding-top: 4px;'>",
            unsafe_allow_html=True,
        )
        if st.button("Esqueceu a senha?", type="secondary", key="btn_open_rec"):
          modal_recuperar_senha()
        st.markdown("</div>", unsafe_allow_html=True)

      st.write("")
      if st.button("Entrar no Sistema", type="primary", use_container_width=True):
        if u_log.strip() and p_log.strip():
          with get_db() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT id, nome, password_hash FROM usuarios WHERE lower(username) = ?",
                (u_log.strip().lower(),),
            )
            usuario = c.fetchone()
            if usuario and usuario["password_hash"] == hash_password(p_log):
              st.session_state["user_id"] = int(usuario["id"])
              st.session_state["user_nome"] = str(usuario["nome"])
              st.rerun()
            else:
              st.error("Usuário ou senha incorretos.")
        else:
          st.warning("Preencha usuário e senha.")

    with tab_cad:
      st.write("")
      c_nome = st.text_input(
          "Nome Completo", key="cad_nome", placeholder="Ex: Arthur Silva"
      )
      c_user = st.text_input(
          "Nome de Usuário Único",
          key="cad_user",
          placeholder="Ex: arthursilva",
      ).lower()
      c_email = st.text_input(
          "E-mail", key="cad_email", placeholder="seuemail@exemplo.com"
      ).lower()
      c_celular = st.text_input(
          "Celular com DDD (WhatsApp)",
          key="cad_cel",
          placeholder="Ex: 11999998888",
      )
      c_pass = st.text_input(
          "Definir Senha",
          type="password",
          key="cad_p",
          placeholder="Mínimo 4 caracteres",
      )
      st.write("")
      if st.button("Criar Minha Conta", use_container_width=True):
        if (
            c_nome.strip()
            and c_user.strip()
            and c_pass.strip()
            and c_email.strip()
            and c_celular.strip()
        ):
          if len(c_pass.strip()) < 4:
            st.error("A senha deve conter no mínimo 4 caracteres.")
          else:
            with get_db() as conn:
              c = conn.cursor()
              c.execute(
                  "SELECT id FROM usuarios WHERE lower(username) = ? OR"
                  " lower(nome) = ?",
                  (c_user.strip().lower(), c_nome.strip().lower()),
              )
              existente = c.fetchone()

              if existente:
                st.error(
                    "❌ Já existe um cadastro com este nome de usuário ou nome"
                    " completo."
                )
              else:
                c.execute(
                    """
                                    INSERT INTO usuarios (username, nome, email, celular, password_hash)
                                    VALUES (?, ?, ?, ?, ?)
                                """,
                    (
                        c_user.strip().lower(),
                        c_nome.strip(),
                        c_email.strip().lower(),
                        c_celular.strip(),
                        hash_password(c_pass),
                    ),
                )
                conn.commit()
                st.success("✅ Conta criada com sucesso! Acesse pela aba 'Acessar'.")
        else:
          st.warning("Preencha todos os campos obrigatórios.")

    st.markdown("</div>", unsafe_allow_html=True)


if not st.session_state["user_id"]:
  tela_autenticacao()
  st.stop()

# --- Painel do Usuário Logado ---
USER_ID = st.session_state["user_id"]

st.sidebar.markdown(f"### Olá, **{st.session_state['user_nome']}** 👋")
if st.sidebar.button("Sair da Conta"):
  st.session_state["user_id"] = None
  st.session_state["user_nome"] = None
  st.rerun()

st.sidebar.divider()

# --- Lançamento Rápido na Barra Lateral ---
st.sidebar.header("➕ Novo Registro")

tipo_mov = st.sidebar.selectbox("Tipo", ["Despesa", "Receita"], key="sb_tipo")

if tipo_mov == "Despesa":
  cats = [
      "Alimentação",
      "Moradia & Contas",
      "Transporte & Veículo",
      "Lazer & Compras",
      "Saúde",
      "Financiamento/Dívida",
      "Outros",
  ]
  metodos_disponiveis = [
      "Boleto",
      "Cartão de Crédito",
      "Pix",
      "Cartão de Débito",
      "Dinheiro",
  ]
else:
  cats = ["Salário Principal", "Vale / Adiantamento", "Extra", "Outros"]
  metodos_disponiveis = ["Pix", "Transferência / TED", "Dinheiro", "Outro"]

metodo_mov = st.sidebar.selectbox(
    "Forma de Pagamento", metodos_disponiveis, key="sb_metodo"
)

# Agora permite parcelas para QUALQUER despesa (Boleto, Cartão de Crédito, Pix, Débito)
num_parcelas = 1
mes_inicio_parcela = date.today().strftime("%Y-%m")

if tipo_mov == "Despesa":
  st.sidebar.markdown("📅 **Parcelamento / Quantidade**")
  num_parcelas = st.sidebar.number_input(
      "Quantidade de Parcelas",
      min_value=1,
      max_value=360,
      value=1,
      step=1,
      key="sb_num_parc",
  )
  if num_parcelas > 1 or metodo_mov == "Cartão de Crédito":
    mes_inicio_parcela = st.sidebar.text_input(
        "Mês da 1ª Parcela/Fatura (AAAA-MM)",
        value=date.today().strftime("%Y-%m"),
        key="sb_mes_ini",
    )

with st.sidebar.form("form_novo_lancamento", clear_on_submit=True):
  data_mov = st.date_input("Data", value=date.today())
  desc_mov = st.text_input(
      "Descrição", placeholder="Ex: Parcela Carro, Supermercado"
  )
  cat_mov = st.selectbox("Categoria", cats)
  ciclo_mov = st.selectbox(
      "Vencimento / Ciclo", ["Dia 05", "Dia 20", "Outro Momento"]
  )
  valor_mov = st.number_input(
      "Valor Total (R$)", min_value=0.01, format="%.2f", step=10.0
  )

  salvar_btn = st.form_submit_button(
      "Salvar Registro", use_container_width=True
  )

  if salvar_btn:
    if desc_mov.strip():
      with get_db() as conn:
        c = conn.cursor()
        # Se for parcelado em mais de 1x
        if tipo_mov == "Despesa" and num_parcelas > 1:
          val_parcela = valor_mov / num_parcelas
          try:
            dt_base = datetime.strptime(mes_inicio_parcela.strip(), "%Y-%m")
          except Exception:
            dt_base = datetime.now()

          for i in range(int(num_parcelas)):
            dt_fat = dt_base + relativedelta(months=i)
            fat_str = dt_fat.strftime("%Y-%m")
            # Ajusta a data de vencimento mês a mês mantendo o dia original
            try:
              data_parcela = date_mov + relativedelta(months=i)
            except Exception:
              data_parcela = date_mov

            desc_parcelada = f"{desc_mov.strip()} ({i + 1}/{num_parcelas})"
            c.execute(
                """
                            INSERT INTO transacoes (usuario_id, data, descricao, tipo, categoria, metodo, ciclo, valor, mes_fatura, parcela_atual, total_parcelas)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                (
                    USER_ID,
                    str(data_parcela),
                    desc_parcelada,
                    tipo_mov,
                    cat_mov,
                    metodo_mov,
                    ciclo_mov,
                    val_parcela,
                    fat_str,
                    i + 1,
                    num_parcelas,
                ),
            )
        else:
          # Lançamento à vista
          fat_unica = (
              mes_inicio_parcela if metodo_mov == "Cartão de Crédito" else None
          )
          c.execute(
              """
                        INSERT INTO transacoes (usuario_id, data, descricao, tipo, categoria, metodo, ciclo, valor, mes_fatura, parcela_atual, total_parcelas)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1)
                    """,
              (
                  USER_ID,
                  str(data_mov),
                  desc_mov.strip(),
                  tipo_mov,
                  cat_mov,
                  metodo_mov,
                  ciclo_mov,
                  valor_mov,
                  fat_unica,
              ),
          )
        conn.commit()
      st.sidebar.success("Registro gravado com sucesso!")
      st.rerun()
    else:
      st.sidebar.error("Informe a descrição.")

# --- Abas Principais ---
tab_dash, tab_ciclos, tab_cartao, tab_parcelas, tab_gestao = st.tabs([
    "📊 Visão Geral do Mês",
    "🗓️ Ciclos Dia 5 / Dia 20",
    "💳 Faturas do Cartão",
    "🚗 Financiamentos & Contratos",
    "⚙️ Editar / Excluir",
])

with get_db() as conn:
  df_trans = pd.read_sql_query(
      "SELECT * FROM transacoes WHERE usuario_id = ? ORDER BY data DESC, id"
      " DESC",
      conn,
      params=(USER_ID,),
  )
  df_parcelas = pd.read_sql_query(
      "SELECT * FROM parcelamentos WHERE usuario_id = ?",
      conn,
      params=(USER_ID,),
  )

# 1. VISÃO GERAL (COMPROMISSOS DO MÊS)
with tab_dash:
  st.subheader("📊 Gastos e Compromissos do Mês")

  mes_atual = date.today().strftime("%Y-%m")
  meses_set = set([mes_atual])

  if not df_trans.empty:
    df_trans["data_dt"] = pd.to_datetime(df_trans["data"])
    df_trans["mes_ano"] = df_trans["data_dt"].dt.strftime("%Y-%m")
    for m in df_trans["mes_ano"].dropna():
      meses_set.add(m)
    for m in df_trans["mes_fatura"].dropna():
      meses_set.add(m)

  meses_ordenados = sorted(list(meses_set), reverse=True)
  idx_padrao = (
      meses_ordenados.index(mes_atual) if mes_atual in meses_ordenados else 0
  )
  mes_selecionado = st.selectbox(
      "Selecione o Mês:", meses_ordenados, index=idx_padrao
  )

  # 1. Cartão de Crédito
  total_cartao_mes = 0.0
  df_cartao_mes = pd.DataFrame()
  if not df_trans.empty:
    df_cartao_mes = df_trans[
        (df_trans["metodo"] == "Cartão de Crédito")
        & (df_trans["mes_fatura"] == mes_selecionado)
        & (df_trans["tipo"] == "Despesa")
    ].copy()
    total_cartao_mes = df_cartao_mes["valor"].sum()

  # 2. Parcelas de Financiamentos Fixos Cadastrados
  total_financiamentos_mes = 0.0
  fin_ativos = pd.DataFrame()
  if not df_parcelas.empty:
    fin_ativos = df_parcelas[
        df_parcelas["parcelas_pagas"] < df_parcelas["total_parcelas"]
    ].copy()
    total_financiamentos_mes = fin_ativos["valor_parcela"].sum()

  # 3. Outros compromissos/boletos/despesas que vencem no mês
  total_outros_mes = 0.0
  df_outros_mes = pd.DataFrame()
  if not df_trans.empty:
    df_outros_mes = df_trans[
        (
            (df_trans["mes_ano"] == mes_selecionado)
            | (df_trans["mes_fatura"] == mes_selecionado)
        )
        & (df_trans["tipo"] == "Despesa")
        & (df_trans["metodo"] != "Cartão de Crédito")
        & (df_trans["categoria"] != "Financiamento/Dívida")
    ].copy()
    total_outros_mes = df_outros_mes["valor"].sum()

  total_gastos_mes = (
      total_cartao_mes + total_financiamentos_mes + total_outros_mes
  )

  # Cards de Resumo
  c1, c2, c3, c4 = st.columns(4)
  c1.metric("💳 Fatura do Cartão", f"R$ {total_cartao_mes:,.2f}")
  c2.metric("🚗 Parcela Financiamento", f"R$ {total_financiamentos_mes:,.2f}")
  c3.metric("📄 Boletos / Outras Contas", f"R$ {total_outros_mes:,.2f}")
  c4.metric(
      f"🔥 TOTAL DO MÊS ({mes_selecionado})",
      f"R$ {total_gastos_mes:,.2f}",
      delta=f"R$ {total_gastos_mes:,.2f}",
      delta_color="inverse",
  )

  st.divider()

  col_det1, col_det2 = st.columns(2)
  with col_det1:
    st.write(f"##### 💳 Detalhes da Fatura do Cartão ({mes_selecionado})")
    if not df_cartao_mes.empty:
      df_cartao_show = df_cartao_mes[[
          "data",
          "descricao",
          "parcela_atual",
          "total_parcelas",
          "valor",
      ]].copy()
      df_cartao_show["valor"] = df_cartao_show["valor"].map(
          "R$ {:,.2f}".format
      )
      st.dataframe(df_cartao_show, use_container_width=True, hide_index=True)
    else:
      st.info("Nenhuma fatura de cartão prevista para este mês.")

  with col_det2:
    st.write("##### 📄 Boletos e Parcelas Deste Mês")
    if not df_outros_mes.empty:
      df_boletos_show = df_outros_mes[[
          "data",
          "descricao",
          "metodo",
          "parcela_atual",
          "total_parcelas",
          "valor",
      ]].copy()
      df_boletos_show["valor"] = df_boletos_show["valor"].map(
          "R$ {:,.2f}".format
      )
      st.dataframe(df_boletos_show, use_container_width=True, hide_index=True)
    else:
      st.info("Nenhum boleto ou despesa avulsa para este mês.")

# 2. SEPARAÇÃO DIA 5 E DIA 20
with tab_ciclos:
  st.subheader("Separação de Gastos por Ciclo de Vencimento")
  if not df_trans.empty:
    df_d = df_trans[df_trans["tipo"] == "Despesa"].copy()
    col5, col20 = st.columns(2)

    with col5:
      st.markdown(
          "<div class='card-ciclo'><h4>🗓️ Contas do Dia 05</h4></div>",
          unsafe_allow_html=True,
      )
      df_5 = df_d[df_d["ciclo"] == "Dia 05"].copy()
      st.metric("Total no Dia 5", f"R$ {df_5['valor'].sum():,.2f}")
      if not df_5.empty:
        df_5_tab = df_5[[
            "id",
            "data",
            "descricao",
            "metodo",
            "categoria",
            "valor",
        ]].copy()
        df_5_tab["valor"] = df_5_tab["valor"].map("R$ {:,.2f}".format)
        st.dataframe(df_5_tab, use_container_width=True, hide_index=True)
      else:
        st.write("Nenhuma conta associada ao Dia 5.")

    with col20:
      st.markdown(
          "<div class='card-ciclo'><h4>🗓️ Contas do Dia 20</h4></div>",
          unsafe_allow_html=True,
      )
      df_20 = df_d[df_d["ciclo"] == "Dia 20"].copy()
      st.metric("Total no Dia 20", f"R$ {df_20['valor'].sum():,.2f}")
      if not df_20.empty:
        df_20_tab = df_20[[
            "id",
            "data",
            "descricao",
            "metodo",
            "categoria",
            "valor",
        ]].copy()
        df_20_tab["valor"] = df_20_tab["valor"].map("R$ {:,.2f}".format)
        st.dataframe(df_20_tab, use_container_width=True, hide_index=True)
      else:
        st.write("Nenhuma conta associada ao Dia 20.")
  else:
    st.info("Sem dados para exibir ciclos.")

# 3. FATURAS DE CARTÃO DE CRÉDITO
with tab_cartao:
  st.subheader("Controle Detalhado de Faturas do Cartão")
  df_card = df_trans[df_trans["metodo"] == "Cartão de Crédito"].copy()
  if not df_card.empty:
    faturas = sorted(df_card["mes_fatura"].dropna().unique(), reverse=True)
    fat_sel = st.selectbox("Selecione a Fatura:", faturas)

    df_fat_view = df_card[df_card["mes_fatura"] == fat_sel]
    st.metric(
        f"Valor Total da Fatura ({fat_sel})",
        f"R$ {df_fat_view['valor'].sum():,.2f}",
    )

    st.write("##### Itens e Parcelas Desta Fatura:")
    df_exibir_fat = df_fat_view[[
        "id",
        "data",
        "descricao",
        "categoria",
        "parcela_atual",
        "total_parcelas",
        "valor",
    ]].copy()
    df_exibir_fat["valor"] = df_exibir_fat["valor"].map("R$ {:,.2f}".format)
    st.dataframe(df_exibir_fat, use_container_width=True, hide_index=True)
  else:
    st.info("Nenhuma compra no Cartão de Crédito lançada ainda.")

# 4. FINANCIAMENTOS E CONTRATOS FIXOS
with tab_parcelas:
  st.subheader("Financiamentos e Despesas Parceladas Fixas")

  with st.expander("➕ Cadastrar Novo Financiamento ou Parcela Fixa"):
    with st.form("form_cad_parcelamento"):
      c_tit = st.text_input(
          "Título do Contrato", placeholder="Ex: Financiamento Veículo"
      )
      c_tipo = st.selectbox(
          "Tipo", ["Financiamento Veículo", "Parcelamento Geral"]
      )
      cp1, cp2 = st.columns(2)
      c_tot_p = cp1.number_input(
          "Total de Parcelas", min_value=2, max_value=360, value=48, step=1
      )
      c_pagas_p = cp2.number_input(
          "Parcelas Já Pagas", min_value=0, max_value=360, value=0, step=1
      )
      cp3, cp4 = st.columns(2)
      c_val_p = cp3.number_input(
          "Valor da Parcela (R$)", min_value=0.01, value=850.0, step=10.0
      )
      c_dia = cp4.selectbox("Dia Fixo de Vencimento", [5, 20, 10, 15, 25, 30])

      btn_fin = st.form_submit_button(
          "Salvar Financiamento", use_container_width=True
      )
      if btn_fin:
        if c_tit.strip():
          with get_db() as conn:
            c = conn.cursor()
            c.execute(
                """
                            INSERT INTO parcelamentos (usuario_id, titulo, tipo_contrato, total_parcelas, parcelas_pagas, valor_parcela, dia_vencimento)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """,
                (
                    USER_ID,
                    c_tit.strip(),
                    c_tipo,
                    int(c_tot_p),
                    int(c_pagas_p),
                    float(c_val_p),
                    int(c_dia),
                ),
            )
            conn.commit()
          st.success("Financiamento cadastrado com sucesso!")
          st.rerun()
        else:
          st.error("Informe o nome do financiamento.")

  if not df_parcelas.empty:
    for _, row in df_parcelas.iterrows():
      cid = int(row["id"])
      tot = int(row["total_parcelas"])
      pagas = int(row["parcelas_pagas"])
      restam = tot - pagas
      val = float(row["valor_parcela"])
      prog = min(pagas / tot, 1.0)
      devedor = restam * val

      st.markdown(f"#### 📌 #{cid} - {row['titulo']} — *{row['tipo_contrato']}*")
      i1, i2, i3 = st.columns(3)
      i1.metric(
          "Parcelas Pagas",
          f"{pagas} / {tot}",
          delta=f"{restam} restantes",
          delta_color="inverse",
      )
      i2.metric("Valor da Parcela", f"R$ {val:,.2f}")
      i3.metric("Saldo Devedor Restante", f"R$ {devedor:,.2f}")

      st.progress(prog)

      col_acao1, col_acao2 = st.columns([2, 3])
      with col_acao1:
        if restam > 0:
          dia_venc = int(row["dia_vencimento"])
          ciclo_autom = (
              f"Dia {dia_venc:02d}"
              if dia_venc in [5, 20]
              else "Outro Momento"
          )
          if st.button(
              f"Pagar Parcela #{pagas + 1} de {tot}",
              key=f"btn_pg_{cid}",
              type="primary",
          ):
            with get_db() as conn:
              c = conn.cursor()
              c.execute(
                  "UPDATE parcelamentos SET parcelas_pagas = parcelas_pagas + 1"
                  " WHERE id = ?",
                  (cid,),
              )
              desc_auto = f"Parcela {pagas + 1}/{tot} - {row['titulo']}"
              c.execute(
                  """
                                INSERT INTO transacoes (usuario_id, data, descricao, tipo, categoria, metodo, ciclo, valor, mes_fatura, parcela_atual, total_parcelas)
                                VALUES (?, ?, ?, 'Despesa', 'Financiamento/Dívida', 'Boleto', ?, ?, ?, ?, ?)
                            """,
                  (
                      USER_ID,
                      str(date.today()),
                      desc_auto,
                      ciclo_autom,
                      val,
                      None,
                      pagas + 1,
                      tot,
                  ),
              )
              conn.commit()
            st.success(f"Parcela #{pagas + 1} paga e lançada nas despesas!")
            st.rerun()
        else:
          st.success("🎉 Financiamento 100% quitado!")
      st.divider()
  else:
    st.info("Nenhum financiamento cadastrado.")

# 5. GERENCIAR, EDITAR E EXCLUIR REGISTROS
with tab_gestao:
  st.subheader("⚙️ Painel de Edição e Exclusão")
  sec_trans, sec_parc = st.tabs(
      ["📝 Editar / Apagar Lançamento", "🚗 Editar / Apagar Financiamento"]
  )

  # SEÇÃO 1: Editar / Apagar Transações
  with sec_trans:
    if not df_trans.empty:
      opcoes_trans = {
          f"#{r['id']} | {r['data']} | {r['descricao']} | R$ {r['valor']:.2f}": (
              int(r["id"])
          )
          for _, r in df_trans.iterrows()
      }
      sel_label = st.selectbox(
          "Escolha o lançamento:", list(opcoes_trans.keys()), key="sel_trans_ed"
      )
      id_edit = opcoes_trans[sel_label]
      registro = df_trans[df_trans["id"] == id_edit].iloc[0]

      st.markdown("---")
      col_ed1, col_ed2 = st.columns(2)

      with col_ed1:
        st.write("##### Corrigir Informações")
        with st.form("form_edita_transacao"):
          ed_desc = st.text_input("Descrição", value=registro["descricao"])
          try:
            dt_val = datetime.strptime(str(registro["data"]), "%Y-%m-%d").date()
          except Exception:
            dt_val = date.today()
          ed_data = st.date_input("Data", value=dt_val)

          lista_tipos = ["Despesa", "Receita"]
          idx_tipo = (
              lista_tipos.index(registro["tipo"])
              if registro["tipo"] in lista_tipos
              else 0
          )
          ed_tipo = st.selectbox("Tipo", lista_tipos, index=idx_tipo)

          lista_cats = [
              "Alimentação",
              "Moradia & Contas",
              "Transporte & Veículo",
              "Lazer & Compras",
              "Saúde",
              "Financiamento/Dívida",
              "Salário Principal",
              "Vale / Adiantamento",
              "Outros",
          ]
          idx_cat = (
              lista_cats.index(registro["categoria"])
              if registro["categoria"] in lista_cats
              else 0
          )
          ed_cat = st.selectbox("Categoria", lista_cats, index=idx_cat)

          lista_met = [
              "Boleto",
              "Cartão de Crédito",
              "Pix",
              "Cartão de Débito",
              "Dinheiro",
          ]
          idx_met = (
              lista_met.index(registro["metodo"])
              if registro["metodo"] in lista_met
              else 0
          )
          ed_met = st.selectbox("Método", lista_met, index=idx_met)

          lista_ciclo = ["Dia 05", "Dia 20", "Outro Momento"]
          idx_ciclo = (
              lista_ciclo.index(registro["ciclo"])
              if registro["ciclo"] in lista_ciclo
              else 2
          )
          ed_ciclo = st.selectbox(
              "Vencimento / Ciclo", lista_ciclo, index=idx_ciclo
          )

          ed_valor = st.number_input(
              "Valor (R$)",
              value=float(registro["valor"]),
              min_value=0.01,
              format="%.2f",
              step=5.0,
          )

          btn_atualizar = st.form_submit_button(
              "Salvar Alterações", type="primary", use_container_width=True
          )
          if btn_atualizar:
            with get_db() as conn:
              c = conn.cursor()
              c.execute(
                  """
                                UPDATE transacoes 
                                SET descricao = ?, data = ?, tipo = ?, categoria = ?, metodo = ?, ciclo = ?, valor = ?
                                WHERE id = ? AND usuario_id = ?
                            """,
                  (
                      ed_desc.strip(),
                      str(ed_data),
                      ed_tipo,
                      ed_cat,
                      ed_met,
                      ed_ciclo,
                      ed_valor,
                      id_edit,
                      USER_ID,
                  ),
              )
              conn.commit()
            st.success("Lançamento atualizado com sucesso!")
            st.rerun()

      with col_ed2:
        st.write("##### Excluir Definitivamente")
        st.warning(
            f"Você está prestes a excluir o lançamento **#{id_edit} -"
            f" {registro['descricao']}**."
        )
        if st.button(
            f"🗑️ Excluir Lançamento #{id_edit}",
            type="secondary",
            use_container_width=True,
        ):
          with get_db() as conn:
            c = conn.cursor()
            c.execute(
                "DELETE FROM transacoes WHERE id = ? AND usuario_id = ?",
                (id_edit, USER_ID),
            )
            conn.commit()
          st.success("Registro excluído com sucesso!")
          st.rerun()
    else:
      st.info("Nenhuma transação encontrada para editar.")

  # SEÇÃO 2: Editar / Apagar Financiamentos
  with sec_parc:
    if not df_parcelas.empty:
      opcoes_parc = {
          f"#{p['id']} | {p['titulo']} ({p['tipo_contrato']})": int(p["id"])
          for _, p in df_parcelas.iterrows()
      }
      sel_p_label = st.selectbox(
          "Escolha o Financiamento:",
          list(opcoes_parc.keys()),
          key="sel_parc_ed",
      )
      id_parc_edit = opcoes_parc[sel_p_label]
      parc_reg = df_parcelas[df_parcelas["id"] == id_parc_edit].iloc[0]

      st.markdown("---")
      col_pe1, col_pe2 = st.columns(2)

      with col_pe1:
        st.write("##### Corrigir Contrato")
        with st.form("form_edita_financiamento"):
          pe_tit = st.text_input("Título", value=parc_reg["titulo"])
          pe_tot = st.number_input(
              "Total de Parcelas",
              value=int(parc_reg["total_parcelas"]),
              min_value=1,
              step=1,
          )
          pe_pagas = st.number_input(
              "Parcelas Pagas",
              value=int(parc_reg["parcelas_pagas"]),
              min_value=0,
              max_value=int(pe_tot),
              step=1,
          )
          pe_val = st.number_input(
              "Valor da Parcela (R$)",
              value=float(parc_reg["valor_parcela"]),
              min_value=0.01,
              format="%.2f",
              step=10.0,
          )

          dias_opc = [5, 20, 10, 15, 25, 30]
          idx_dia = (
              dias_opc.index(parc_reg["dia_vencimento"])
              if parc_reg["dia_vencimento"] in dias_opc
              else 0
          )
          pe_dia = st.selectbox(
              "Dia de Vencimento", dias_opc, index=idx_dia, key="ed_dia_v"
          )

          btn_atualiza_parc = st.form_submit_button(
              "Atualizar Contrato", type="primary", use_container_width=True
          )
          if btn_atualiza_parc:
            with get_db() as conn:
              c = conn.cursor()
              c.execute(
                  """
                                UPDATE parcelamentos 
                                SET titulo = ?, total_parcelas = ?, parcelas_pagas = ?, valor_parcela = ?, dia_vencimento = ?
                                WHERE id = ? AND usuario_id = ?
                            """,
                  (
                      pe_tit.strip(),
                      int(pe_tot),
                      int(pe_pagas),
                      float(pe_val),
                      int(pe_dia),
                      id_parc_edit,
                      USER_ID,
                  ),
              )
              conn.commit()
            st.success("Financiamento atualizado com sucesso!")
            st.rerun()

      with col_pe2:
        st.write("##### Excluir Financiamento")
        st.warning(
            f"Excluir o contrato **{parc_reg['titulo']}** removerá o"
            " acompanhamento."
        )
        if st.button(
            f"🗑️ Excluir Financiamento #{id_parc_edit}",
            type="secondary",
            use_container_width=True,
        ):
          with get_db() as conn:
            c = conn.cursor()
            c.execute(
                "DELETE FROM parcelamentos WHERE id = ? AND usuario_id = ?",
                (id_parc_edit, USER_ID),
            )
            conn.commit()
          st.success("Contrato excluído com sucesso!")
          st.rerun()
    else:
      st.info("Nenhum financiamento cadastrado para gerenciar.")