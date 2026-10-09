import hashlib
import re
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
    # 1. Utilizadores
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
                dia_vencimento INTEGER NOT NULL,
                data_inicio TEXT
            )
        """)

    try:
      c.execute("ALTER TABLE parcelamentos ADD COLUMN data_inicio TEXT")
    except sqlite3.OperationalError:
      pass

    conn.commit()


init_db()

# --- Configuração Visual Global ---
st.set_page_config(
    page_title="Apex Finance | Gestão Pessoal",
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

# Gestão de Sessão
if "user_id" not in st.session_state:
  st.session_state["user_id"] = None
if "user_nome" not in st.session_state:
  st.session_state["user_nome"] = None


# --- Janela de Recuperação de Senha ---
@st.dialog("🔑 Recuperação de Acesso")
def modal_recuperar_senha():
  st.caption(
      "Indique o seu nome de utilizador e o e-mail ou telemóvel registado para"
      " validar a sua identidade."
  )
  r_user = st.text_input(
      "Nome de Utilizador",
      key="rec_u",
      placeholder="Introduza o nome de utilizador",
  ).lower()
  r_contato = st.text_input(
      "E-mail ou Telemóvel Registado",
      key="rec_cont",
      placeholder="exemplo@email.com ou 11999998888",
  ).lower()
  r_new_pass = st.text_input(
      "Nova Palavra-passe",
      type="password",
      key="rec_np",
      placeholder="Mínimo 4 caracteres",
  )

  st.write("")
  if st.button("Guardar Nova Palavra-passe", type="primary", use_container_width=True):
    if r_user.strip() and r_contato.strip() and r_new_pass.strip():
      if len(r_new_pass.strip()) < 4:
        st.error("A nova palavra-passe deve ter no mínimo 4 caracteres.")
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
                "🎉 Palavra-passe alterada com sucesso! Feche esta janela para"
                " iniciar sessão."
            )
          else:
            st.error("Os dados introduzidos não coincidem com o registo.")
    else:
      st.warning("Preencha todos os campos obrigatórios.")


# --- Ecrã de Autenticação ---
def tela_autenticacao():
  _, col_centro, _ = st.columns([1, 1.4, 1])

  with col_centro:
    st.markdown(
        """
        <div class="login-box">
            <div class="login-header">
                <div class="login-title">💼 Apex Finance</div>
                <div class="login-subtitle">Gestão Financeira & Controlo Inteligente</div>
            </div>
        """,
        unsafe_allow_html=True,
    )

    tab_log, tab_cad = st.tabs(["🔐 Entrar", "📝 Criar Conta"])

    with tab_log:
      st.write("")
      u_log = st.text_input(
          "Nome de Utilizador",
          key="txt_login_u",
          placeholder="Introduza o seu utilizador",
      )
      p_log = st.text_input(
          "Palavra-passe",
          type="password",
          key="txt_login_p",
          placeholder="Introduza a sua palavra-passe",
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
              st.error("Utilizador ou palavra-passe incorretos.")
        else:
          st.warning("Preencha o utilizador e a palavra-passe.")

    with tab_cad:
      st.write("")
      c_nome = st.text_input(
          "Nome Completo", key="cad_nome", placeholder="Ex: Arthur Silva"
      )
      c_user = st.text_input(
          "Nome de Utilizador Único",
          key="cad_user",
          placeholder="Ex: arthursilva",
      ).lower()
      c_email = st.text_input(
          "E-mail", key="cad_email", placeholder="seuemail@exemplo.com"
      ).lower()
      c_celular = st.text_input(
          "Telemóvel com DDD",
          key="cad_cel",
          placeholder="Ex: 11999998888",
      )
      c_pass = st.text_input(
          "Definir Palavra-passe",
          type="password",
          key="cad_p",
          placeholder="Mínimo 4 caracteres",
      )
      st.write("")
      if st.button("Criar Conta", use_container_width=True):
        if (
            c_nome.strip()
            and c_user.strip()
            and c_pass.strip()
            and c_email.strip()
            and c_celular.strip()
        ):
          if len(c_pass.strip()) < 4:
            st.error("A palavra-passe deve conter pelo menos 4 caracteres.")
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
                    "❌ Já existe uma conta com este nome de utilizador ou nome"
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
                st.success("✅ Conta registada com sucesso! Aceda ao separador 'Entrar'.")
        else:
          st.warning("Preencha todos os campos obrigatórios.")

    st.markdown("</div>", unsafe_allow_html=True)


if not st.session_state["user_id"]:
  tela_autenticacao()
  st.stop()

# --- Painel do Utilizador ---
USER_ID = st.session_state["user_id"]

st.sidebar.markdown(f"### Olá, **{st.session_state['user_nome']}** 👋")
if st.sidebar.button("Terminar Sessão"):
  st.session_state["user_id"] = None
  st.session_state["user_nome"] = None
  st.rerun()

st.sidebar.divider()

# --- Barra Lateral: Lançamento Rápido ---
st.sidebar.header("➕ Novo Registo")

tipo_mov = st.sidebar.selectbox("Tipo", ["Despesa", "Receita"], key="sb_tipo")

if tipo_mov == "Despesa":
  cats = [
      "Financiamento/Dívida",
      "Moradia & Contas",
      "Transporte & Veículo",
      "Alimentação",
      "Lazer & Compras",
      "Saúde",
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

cat_mov = st.sidebar.selectbox("Categoria", cats, key="sb_cat_mov")
metodo_mov = st.sidebar.selectbox(
    "Forma de Pagamento", metodos_disponiveis, key="sb_metodo"
)

num_parcelas = 1
data_primeira_cobranca = date.today()

if tipo_mov == "Despesa":
  st.sidebar.markdown("📅 **Parcelamento & Prazos**")
  num_parcelas = st.sidebar.number_input(
      "Quantidade de Prestações",
      min_value=1,
      max_value=360,
      value=12 if cat_mov == "Financiamento/Dívida" else 1,
      step=1,
      key="sb_num_parc",
  )
  data_primeira_cobranca = st.sidebar.date_input(
      "Data da 1ª Cobrança / Início",
      value=date.today(),
      key="sb_dt_primeira_cobranca",
  )

with st.sidebar.form("form_novo_lancamento", clear_on_submit=True):
  desc_mov = st.text_input(
      "Descrição",
      placeholder="Ex: Financiamento Onix, Parcela Seguro, Supermercado",
  )
  ciclo_mov = st.selectbox(
      "Vencimento / Ciclo", ["Dia 05", "Dia 20", "Outro Momento"]
  )
  tipo_valor = st.radio(
      "O valor informado abaixo é:",
      ["Valor da Parcela Mensal", "Valor Total da Compra"],
      index=0 if cat_mov == "Financiamento/Dívida" else 1,
  )
  valor_input = st.number_input(
      "Valor (R$)", min_value=0.01, format="%.2f", step=50.0
  )

  salvar_btn = st.form_submit_button(
      "Guardar Registo", use_container_width=True
  )

  if salvar_btn:
    if desc_mov.strip():
      with get_db() as conn:
        c = conn.cursor()

        if tipo_mov == "Despesa" and num_parcelas > 1:
          val_parcela = (
              valor_input
              if tipo_valor == "Valor da Parcela Mensal"
              else (valor_input / num_parcelas)
          )

          if cat_mov == "Financiamento/Dívida":
            dia_v = data_primeira_cobranca.day
            c.execute(
                """
                            INSERT INTO parcelamentos (usuario_id, titulo, tipo_contrato, total_parcelas, parcelas_pagas, valor_parcela, dia_vencimento, data_inicio)
                            VALUES (?, ?, ?, ?, 0, ?, ?, ?)
                        """,
                (
                    USER_ID,
                    desc_mov.strip(),
                    "Financiamento Veículo"
                    if "veiculo" in desc_mov.lower()
                    or "veículo" in desc_mov.lower()
                    or "onix" in desc_mov.lower()
                    else "Parcelamento Geral",
                    int(num_parcelas),
                    float(val_parcela),
                    int(dia_v),
                    str(data_primeira_cobranca),
                ),
            )

          for i in range(int(num_parcelas)):
            dt_parcela = data_primeira_cobranca + relativedelta(months=i)
            fat_str = dt_parcela.strftime("%Y-%m")
            desc_parcelada = f"{desc_mov.strip()} ({i + 1}/{num_parcelas})"
            c.execute(
                """
                            INSERT INTO transacoes (usuario_id, data, descricao, tipo, categoria, metodo, ciclo, valor, mes_fatura, parcela_atual, total_parcelas)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                (
                    USER_ID,
                    str(dt_parcela),
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
          fat_unica = (
              data_primeira_cobranca.strftime("%Y-%m")
              if metodo_mov == "Cartão de Crédito"
              else None
          )
          c.execute(
              """
                        INSERT INTO transacoes (usuario_id, data, descricao, tipo, categoria, metodo, ciclo, valor, mes_fatura, parcela_atual, total_parcelas)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1)
                    """,
              (
                  USER_ID,
                  str(data_primeira_cobranca),
                  desc_mov.strip(),
                  tipo_mov,
                  cat_mov,
                  metodo_mov,
                  ciclo_mov,
                  valor_input,
                  fat_unica,
              ),
          )
        conn.commit()
      st.sidebar.success("Gravado com sucesso!")
      st.rerun()
    else:
      st.sidebar.error("Indique uma descrição válida.")

# --- Carregar Dados do Banco ---
with get_db() as conn:
  df_trans = pd.read_sql_query(
      "SELECT * FROM transacoes WHERE usuario_id = ? ORDER BY data ASC, id"
      " ASC",
      conn,
      params=(USER_ID,),
  )
  df_parcelas = pd.read_sql_query(
      "SELECT * FROM parcelamentos WHERE usuario_id = ?",
      conn,
      params=(USER_ID,),
  )

if not df_trans.empty:
  df_trans["data_dt"] = pd.to_datetime(df_trans["data"])
  df_trans["mes_ano"] = df_trans["data_dt"].dt.strftime("%Y-%m")
else:
  df_trans["mes_ano"] = []

# Mapeia todos os meses existentes
meses_set = set([date.today().strftime("%Y-%m")])
if not df_trans.empty:
  for m in df_trans["mes_ano"].dropna():
    meses_set.add(m)
  for m in df_trans["mes_fatura"].dropna():
    meses_set.add(m)

# Inclui os meses futuros dos financiamentos ativos da tabela parcelamentos
if not df_parcelas.empty:
  for _, p_row in df_parcelas.iterrows():
    if "data_inicio" in p_row and p_row["data_inicio"]:
      try:
        dt_ini = datetime.strptime(str(p_row["data_inicio"]), "%Y-%m-%d").date()
        for k in range(int(p_row["total_parcelas"])):
          m_futuro = (dt_ini + relativedelta(months=k)).strftime("%Y-%m")
          meses_set.add(m_futuro)
      except Exception:
        pass

meses_ordenados = sorted(list(meses_set), reverse=True)
mes_atual = date.today().strftime("%Y-%m")
idx_padrao = (
    meses_ordenados.index(mes_atual) if mes_atual in meses_ordenados else 0
)

# --- Separadores de Navegação ---
tab_dash, tab_ciclos, tab_cartao, tab_parcelas, tab_gestao = st.tabs([
    "📊 Visão Geral do Mês",
    "🗓️ Ciclos Dia 5 / Dia 20",
    "💳 Faturas do Cartão",
    "🚗 Financiamentos & Contratos",
    "⚙️ Editar / Excluir",
])

# 1. VISÃO GERAL DO MÊS (AJUSTE ROBUSTO DA PARCELA DO FINANCIAMENTO)
with tab_dash:
  st.subheader("📊 Gastos e Compromissos do Mês")

  mes_selecionado = st.selectbox(
      "Selecione o Mês:",
      meses_ordenados,
      index=idx_padrao,
      key="sel_mes_visao_geral",
  )

  # A) Fatura Cartão
  df_cartao_mes = pd.DataFrame()
  if not df_trans.empty:
    df_cartao_mes = df_trans[
        (df_trans["metodo"] == "Cartão de Crédito")
        & (df_trans["mes_fatura"] == mes_selecionado)
        & (df_trans["tipo"] == "Despesa")
    ].copy()
  total_cartao_mes = (
      df_cartao_mes["valor"].sum() if not df_cartao_mes.empty else 0.0
  )

  # B) Parcela de Financiamento que vence NO MÊS
  # 1. Busca por transações registradas no mês que sejam de Financiamento/Dívida ou tenham financiamento na descrição
  df_fin_mes = pd.DataFrame()
  if not df_trans.empty:
    filtro_fin = (
        (df_trans["mes_ano"] == mes_selecionado)
        & (df_trans["tipo"] == "Despesa")
        & (
            df_trans["categoria"].str.contains("Financiamento", case=False, na=False)
            | df_trans["descricao"].str.contains("Financiamento", case=False, na=False)
        )
    )
    df_fin_mes = df_trans[filtro_fin].copy()

  total_financiamentos_mes = (
      df_fin_mes["valor"].sum() if not df_fin_mes.empty else 0.0
  )

  # 2. Se não houver transações individuais lançadas para este mês, calcula a partir dos contratos cadastrados em parcelamentos
  if total_financiamentos_mes == 0.0 and not df_parcelas.empty:
    for _, parc_item in df_parcelas.iterrows():
      tot_p = int(parc_item["total_parcelas"])
      pagas_p = int(parc_item["parcelas_pagas"])
      if pagas_p < tot_p:
        # Verifica se o mês selecionado está no período de cobrança deste contrato
        if "data_inicio" in parc_item and parc_item["data_inicio"]:
          try:
            d_ini = datetime.strptime(str(parc_item["data_inicio"]), "%Y-%m-%d").date()
            meses_contrato = [
                (d_ini + relativedelta(months=idx)).strftime("%Y-%m")
                for idx in range(pagas_p, tot_p)
            ]
            if mes_selecionado in meses_contrato:
              total_financiamentos_mes += float(parc_item["valor_parcela"])
          except Exception:
            total_financiamentos_mes += float(parc_item["valor_parcela"])
        else:
          total_financiamentos_mes += float(parc_item["valor_parcela"])

  # C) Outras Contas / Boletos do Mês
  df_outros_mes = pd.DataFrame()
  if not df_trans.empty:
    filtro_outros = (
        (df_trans["mes_ano"] == mes_selecionado)
        & (df_trans["tipo"] == "Despesa")
        & (df_trans["metodo"] != "Cartão de Crédito")
        & (
            ~df_trans["categoria"].str.contains("Financiamento", case=False, na=False)
        )
        & (
            ~df_trans["descricao"].str.contains("Financiamento", case=False, na=False)
        )
    )
    df_outros_mes = df_trans[filtro_outros].copy()
  total_outros_mes = (
      df_outros_mes["valor"].sum() if not df_outros_mes.empty else 0.0
  )

  total_gastos_mes = (
      total_cartao_mes + total_financiamentos_mes + total_outros_mes
  )

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
    st.write(
        f"##### 🚗 Parcelas de Financiamentos & Boletos ({mes_selecionado})"
    )
    df_compr_mes = pd.concat([df_fin_mes, df_outros_mes])
    if not df_compr_mes.empty:
      df_compr_show = df_compr_mes[[
          "data",
          "descricao",
          "categoria",
          "metodo",
          "parcela_atual",
          "total_parcelas",
          "valor",
      ]].copy()
      df_compr_show["valor"] = df_compr_show["valor"].map("R$ {:,.2f}".format)
      st.dataframe(df_compr_show, use_container_width=True, hide_index=True)
    elif total_financiamentos_mes > 0:
      st.info(
          f"Existe parcela de financiamento ativa de R$"
          f" {total_financiamentos_mes:,.2f} prevista para este mês."
      )
    else:
      st.info("Nenhum boleto ou parcela de financiamento para este mês.")

# 2. CICLOS DIA 5 E DIA 20
with tab_ciclos:
  st.subheader("Separação de Gastos por Ciclo de Vencimento")
  mes_ciclo_sel = st.selectbox(
      "Visualizar Ciclos do Mês:",
      meses_ordenados,
      index=idx_padrao,
      key="sel_mes_ciclos",
  )

  if not df_trans.empty:
    df_ciclos_mes = df_trans[
        (df_trans["mes_ano"] == mes_ciclo_sel)
        & (df_trans["tipo"] == "Despesa")
    ].copy()
    col5, col20 = st.columns(2)

    with col5:
      st.markdown(
          f"<div class='card-ciclo'><h4>🗓️ Contas do Dia 05"
          f" ({mes_ciclo_sel})</h4></div>",
          unsafe_allow_html=True,
      )
      df_5 = df_ciclos_mes[df_ciclos_mes["ciclo"] == "Dia 05"].copy()
      st.metric(f"Total no Dia 5 ({mes_ciclo_sel})", f"R$ {df_5['valor'].sum():,.2f}")
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
        st.write("Nenhuma conta associada ao Dia 5 neste mês.")

    with col20:
      st.markdown(
          f"<div class='card-ciclo'><h4>🗓️ Contas do Dia 20"
          f" ({mes_ciclo_sel})</h4></div>",
          unsafe_allow_html=True,
      )
      df_20 = df_ciclos_mes[df_ciclos_mes["ciclo"] == "Dia 20"].copy()
      st.metric(
          f"Total no Dia 20 ({mes_ciclo_sel})", f"R$ {df_20['valor'].sum():,.2f}"
      )
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
        st.write("Nenhuma conta associada ao Dia 20 neste mês.")
  else:
    st.info("Sem dados para exibir ciclos.")

# 3. FATURAS DO CARTÃO
with tab_cartao:
  st.subheader("Controlo Detalhado de Faturas do Cartão")
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
    st.info("Nenhuma compra efetuada no Cartão de Crédito.")

# 4. FINANCIAMENTOS E CONTRATOS FIXOS
with tab_parcelas:
  st.subheader("Financiamentos e Despesas Parceladas Fixas")

  with st.expander("➕ Registar Novo Financiamento ou Parcela Fixa Manualmente"):
    with st.form("form_cad_parcelamento_tab"):
      c_tit = st.text_input(
          "Título do Contrato", placeholder="Ex: Financiamento Chevrolet Onix"
      )
      c_tipo = st.selectbox(
          "Tipo", ["Financiamento Veículo", "Parcelamento Geral"]
      )
      cp1, cp2 = st.columns(2)
      c_tot_p = cp1.number_input(
          "Total de Prestações", min_value=2, max_value=360, value=48, step=1
      )
      c_pagas_p = cp2.number_input(
          "Prestações Já Amortizadas", min_value=0, max_value=360, value=0, step=1
      )
      cp3, cp4, cp5 = st.columns(3)
      c_val_p = cp3.number_input(
          "Valor da Parcela (R$)", min_value=0.01, value=1300.0, step=50.0
      )
      c_dia = cp4.selectbox("Dia Fixo de Vencimento", [5, 20, 10, 15, 25, 30])
      c_dt_inicio = cp5.date_input(
          "Data da 1ª Cobrança / Início", value=date.today()
      )

      btn_fin = st.form_submit_button(
          "Guardar Financiamento", use_container_width=True
      )
      if btn_fin:
        nome_valido = c_tit.strip() if c_tit else ""
        if nome_valido:
          with get_db() as conn:
            c = conn.cursor()
            c.execute(
                """
                            INSERT INTO parcelamentos (usuario_id, titulo, tipo_contrato, total_parcelas, parcelas_pagas, valor_parcela, dia_vencimento, data_inicio)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                (
                    USER_ID,
                    nome_valido,
                    c_tipo,
                    int(c_tot_p),
                    int(c_pagas_p),
                    float(c_val_p),
                    int(c_dia),
                    str(c_dt_inicio),
                ),
            )

            ciclo_calc = (
                f"Dia {int(c_dia):02d}"
                if int(c_dia) in [5, 20]
                else "Outro Momento"
            )
            for i in range(int(c_pagas_p), int(c_tot_p)):
              dt_p = c_dt_inicio + relativedelta(months=i)
              fat_s = dt_p.strftime("%Y-%m")
              desc_p = f"{nome_valido} ({i + 1}/{int(c_tot_p)})"
              c.execute(
                  """
                                INSERT INTO transacoes (usuario_id, data, descricao, tipo, categoria, metodo, ciclo, valor, mes_fatura, parcela_atual, total_parcelas)
                                VALUES (?, ?, ?, 'Despesa', 'Financiamento/Dívida', 'Boleto', ?, ?, ?, ?, ?)
                            """,
                  (
                      USER_ID,
                      str(dt_p),
                      desc_p,
                      ciclo_calc,
                      float(c_val_p),
                      fat_s,
                      i + 1,
                      int(c_tot_p),
                  ),
              )
            conn.commit()
          st.success(
              "Financiamento guardado e parcelas integradas à agenda mensal!"
          )
          st.rerun()
        else:
          st.error("Indique o nome do financiamento.")

  if not df_parcelas.empty:
    for _, row in df_parcelas.iterrows():
      cid = int(row["id"])
      tot = int(row["total_parcelas"])
      pagas = int(row["parcelas_pagas"])
      restam = tot - pagas
      val = float(row["valor_parcela"])
      prog = min(pagas / tot, 1.0)
      devedor = restam * val
      dt_inicio_exibir = (
          row["data_inicio"] if "data_inicio" in row and row["data_inicio"] else ""
      )

      st.markdown(
          f"#### 📌 #{cid} - {row['titulo']} — *{row['tipo_contrato']}*"
          + (
              f"  <small style='color:#94a3b8;'>(Início: {dt_inicio_exibir})</small>"
              if dt_inicio_exibir
              else ""
          ),
          unsafe_allow_html=True,
      )
      i1, i2, i3 = st.columns(3)
      i1.metric(
          "Prestações Pagas",
          f"{pagas} / {tot}",
          delta=f"{restam} restantes",
          delta_color="inverse",
      )
      i2.metric("Valor da Parcela", f"R$ {val:,.2f}")
      i3.metric("Saldo Devedor Estimado", f"R$ {devedor:,.2f}")

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
              f"Marcar Parcela #{pagas + 1} como Paga",
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
              conn.commit()
            st.success(f"Parcela #{pagas + 1} amortizada com sucesso!")
            st.rerun()
        else:
          st.success("🎉 Financiamento totalmente liquidado!")
      st.divider()
  else:
    st.info(
        "Nenhum contrato ativo listado. Utilize o formulário acima para"
        " cadastrar o acompanhamento de longo prazo."
    )

# 5. GERENCIAR, EDITAR E EXCLUIR (AGRUPADO INTELIGENTEMENTE)
with tab_gestao:
  st.subheader("⚙️ Painel de Edição e Eliminação Agrupado")
  st.caption(
      "Edite compras parceladas ou financiamentos em bloco, ou ajuste"
      " lançamentos individuais."
  )

  sec_pacotes, sec_avulsas, sec_contratos = st.tabs([
      "📦 Compras e Financiamentos Parcelados",
      "📝 Lançamentos Individuais / Avulsos",
      "🚗 Contratos de Financiamento",
  ])

  # --- 1. PACOTES PARCELADOS (AGRUPADOS) ---
  with sec_pacotes:
    if not df_trans.empty:
      df_com_parcelas = df_trans.copy()

      def obter_nome_base(desc):
        return re.sub(r"\s*\(\d+/\d+\)\s*$", "", str(desc)).strip()

      df_com_parcelas["nome_base"] = df_com_parcelas["descricao"].apply(
          obter_nome_base
      )

      contagem = (
          df_com_parcelas.groupby(["nome_base", "metodo"])
          .size()
          .reset_index(name="qtd")
      )
      pacotes_identificados = contagem[contagem["qtd"] > 1]

      if not pacotes_identificados.empty:
        opcoes_pacotes = {}
        for _, p_row in pacotes_identificados.iterrows():
          n_base = p_row["nome_base"]
          m_base = p_row["metodo"]
          qtd_p = p_row["qtd"]
          val_total = df_com_parcelas[
              (df_com_parcelas["nome_base"] == n_base)
              & (df_com_parcelas["metodo"] == m_base)
          ]["valor"].sum()
          label = f"{n_base} ({qtd_p} parcelas) | {m_base} | Total: R$ {val_total:,.2f}"
          opcoes_pacotes[label] = (n_base, m_base)

        pacote_selecionado = st.selectbox(
            "Selecione o Pacote / Financiamento Agrupado:",
            list(opcoes_pacotes.keys()),
            key="sel_pacote_group",
        )
        base_nome, base_metodo = opcoes_pacotes[pacote_selecionado]

        df_grupo = df_com_parcelas[
            (df_com_parcelas["nome_base"] == base_nome)
            & (df_com_parcelas["metodo"] == base_metodo)
        ].copy()

        st.markdown("---")
        st.write(f"##### 📋 Todas as Parcelas de: **{base_nome}**")
        df_exibir_grupo = df_grupo[[
            "id",
            "data",
            "descricao",
            "categoria",
            "metodo",
            "ciclo",
            "valor",
        ]].copy()
        df_exibir_grupo["valor"] = df_exibir_grupo["valor"].map(
            "R$ {:,.2f}".format
        )
        st.dataframe(df_exibir_grupo, use_container_width=True, hide_index=True)

        col_g_edit, col_g_del = st.columns(2)

        with col_g_edit:
          st.write("##### ✏️ Atualizar Todas as Parcelas Deste Pacote")
          with st.form("form_edita_grupo"):
            novo_nome_base = st.text_input("Novo Nome Base", value=base_nome)
            primeira_linha = df_grupo.iloc[0]

            lista_cats = [
                "Financiamento/Dívida",
                "Moradia & Contas",
                "Transporte & Veículo",
                "Alimentação",
                "Lazer & Compras",
                "Saúde",
                "Outros",
            ]
            idx_cat_g = (
                lista_cats.index(primeira_linha["categoria"])
                if primeira_linha["categoria"] in lista_cats
                else 0
            )
            nova_cat_g = st.selectbox(
                "Categoria de Todas", lista_cats, index=idx_cat_g
            )

            lista_ciclo_g = ["Dia 05", "Dia 20", "Outro Momento"]
            idx_ciclo_g = (
                lista_ciclo_g.index(primeira_linha["ciclo"])
                if primeira_linha["ciclo"] in lista_ciclo_g
                else 2
            )
            novo_ciclo_g = st.selectbox(
                "Ciclo de Vencimento", lista_ciclo_g, index=idx_ciclo_g
            )

            novo_val_parc = st.number_input(
                "Novo Valor de Cada Parcela (R$)",
                value=float(primeira_linha["valor"]),
                min_value=0.01,
                format="%.2f",
                step=10.0,
            )

            btn_atualizar_grupo = st.form_submit_button(
                "Atualizar Todas as Parcelas",
                type="primary",
                use_container_width=True,
            )
            if btn_atualizar_grupo:
              ids_grupo = df_grupo["id"].tolist()
              with get_db() as conn:
                c = conn.cursor()
                for _, r_item in df_grupo.iterrows():
                  p_atual = r_item["parcela_atual"]
                  p_total = r_item["total_parcelas"]
                  novo_desc_item = f"{novo_nome_base.strip()} ({p_atual}/{p_total})"
                  c.execute(
                      """
                                        UPDATE transacoes 
                                        SET descricao = ?, categoria = ?, ciclo = ?, valor = ?
                                        WHERE id = ? AND usuario_id = ?
                                    """,
                      (
                          novo_desc_item,
                          nova_cat_g,
                          novo_ciclo_g,
                          novo_val_parc,
                          r_item["id"],
                          USER_ID,
                      ),
                  )
                conn.commit()
              st.success(
                  f"Todas as {len(ids_grupo)} parcelas foram atualizadas com"
                  " sucesso!"
              )
              st.rerun()

        with col_g_del:
          st.write("##### 🗑️ Excluir Pacote Inteiro")
          st.error(
              f"Esta ação irá remover permanentemente **todas as"
              f" {len(df_grupo)} parcelas** de **{base_nome}** do seu"
              " extrato."
          )
          if st.button(
              f"Excluir Todas as {len(df_grupo)} Parcelas de {base_nome}",
              type="secondary",
              use_container_width=True,
          ):
            ids_para_apagar = df_grupo["id"].tolist()
            with get_db() as conn:
              c = conn.cursor()
              c.executemany(
                  "DELETE FROM transacoes WHERE id = ? AND usuario_id = ?",
                  [(i, USER_ID) for i in ids_para_apagar],
              )
              conn.commit()
            st.success(
                f"Todas as {len(ids_para_apagar)} parcelas foram eliminadas!"
            )
            st.rerun()
      else:
        st.info("Nenhuma compra parcelada ou financiamento em grupo ativo.")
    else:
      st.info("Sem lançamentos cadastrados.")

  # --- 2. LANÇAMENTOS INDIVIDUAIS / AVULSOS ---
  with sec_avulsas:
    if not df_trans.empty:
      df_avulsas = df_trans[df_trans["total_parcelas"] <= 1].copy()
      if not df_avulsas.empty:
        opcoes_avulsas = {
            f"#{r['id']} | {r['data']} | {r['descricao']} | R$ {r['valor']:.2f}": (
                int(r["id"])
            )
            for _, r in df_avulsas.iterrows()
        }
        sel_avulsa_label = st.selectbox(
            "Selecione o Lançamento Individual:",
            list(opcoes_avulsas.keys()),
            key="sel_trans_avulsa",
        )
        id_avulsa = opcoes_avulsas[sel_avulsa_label]
        reg_avulso = df_avulsas[df_avulsas["id"] == id_avulsa].iloc[0]

        st.markdown("---")
        col_av1, col_av2 = st.columns(2)

        with col_av1:
          st.write("##### Corrigir Registro")
          with st.form("form_edita_avulso"):
            ed_desc = st.text_input("Descrição", value=reg_avulso["descricao"])
            try:
              dt_val = datetime.strptime(
                  str(reg_avulso["data"]), "%Y-%m-%d"
              ).date()
            except Exception:
              dt_val = date.today()
            ed_data = st.date_input("Data", value=dt_val)

            lista_tipos = ["Despesa", "Receita"]
            idx_tipo = (
                lista_tipos.index(reg_avulso["tipo"])
                if reg_avulso["tipo"] in lista_tipos
                else 0
            )
            ed_tipo = st.selectbox("Tipo", lista_tipos, index=idx_tipo)

            lista_cats = [
                "Moradia & Contas",
                "Transporte & Veículo",
                "Alimentação",
                "Lazer & Compras",
                "Saúde",
                "Salário Principal",
                "Vale / Adiantamento",
                "Outros",
            ]
            idx_cat = (
                lista_cats.index(reg_avulso["categoria"])
                if reg_avulso["categoria"] in lista_cats
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
                lista_met.index(reg_avulso["metodo"])
                if reg_avulso["metodo"] in lista_met
                else 0
            )
            ed_met = st.selectbox("Método", lista_met, index=idx_met)

            lista_ciclo = ["Dia 05", "Dia 20", "Outro Momento"]
            idx_ciclo = (
                lista_ciclo.index(reg_avulso["ciclo"])
                if reg_avulso["ciclo"] in lista_ciclo
                else 2
            )
            ed_ciclo = st.selectbox(
                "Vencimento / Ciclo", lista_ciclo, index=idx_ciclo
            )

            ed_valor = st.number_input(
                "Valor (R$)",
                value=float(reg_avulso["valor"]),
                min_value=0.01,
                format="%.2f",
                step=5.0,
            )

            btn_atualizar = st.form_submit_button(
                "Guardar Alterações", type="primary", use_container_width=True
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
                        id_avulsa,
                        USER_ID,
                    ),
                )
                conn.commit()
              st.success("Registo atualizado com sucesso!")
              st.rerun()

        with col_av2:
          st.write("##### Eliminar Registro")
          st.warning(
              f"Excluir definitivamente o registro **#{id_avulsa} -"
              f" {reg_avulso['descricao']}**."
          )
          if st.button(
              f"🗑️ Eliminar Registo #{id_avulsa}",
              type="secondary",
              use_container_width=True,
          ):
            with get_db() as conn:
              c = conn.cursor()
              c.execute(
                  "DELETE FROM transacoes WHERE id = ? AND usuario_id = ?",
                  (id_avulsa, USER_ID),
              )
              conn.commit()
            st.success("Registro eliminado com sucesso!")
            st.rerun()
      else:
        st.info("Nenhum lançamento avulso encontrado.")
    else:
      st.info("Nenhuma transação disponível para edição.")

  # --- 3. CONTRATOS DE FINANCIAMENTO ---
  with sec_contratos:
    if not df_parcelas.empty:
      opcoes_parc = {
          f"#{p['id']} | {p['titulo']} ({p['tipo_contrato']})": int(p["id"])
          for _, p in df_parcelas.iterrows()
      }
      sel_p_label = st.selectbox(
          "Selecione o Financiamento:",
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
              "Total de Prestações",
              value=int(parc_reg["total_parcelas"]),
              min_value=1,
              step=1,
          )
          pe_pagas = st.number_input(
              "Prestações Já Amortizadas",
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
        st.write("##### Eliminar Financiamento")
        st.warning(
            f"Eliminar o contrato **{parc_reg['titulo']}** remove o"
            " acompanhamento geral."
        )
        if st.button(
            f"🗑️ Eliminar Financiamento #{id_parc_edit}",
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
          st.success("Contrato eliminado com sucesso!")
          st.rerun()
    else:
      st.info("Nenhum financiamento registado para gerir.")