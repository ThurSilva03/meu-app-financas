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
                total_parcelas INTEGER DEFAULT 1,
                pago INTEGER DEFAULT 0
            )
        """)

    colunas_extras = [
        ("usuario_id", "INTEGER DEFAULT 1"),
        ("metodo", "TEXT NOT NULL DEFAULT 'Pix'"),
        ("ciclo", "TEXT DEFAULT 'Outro'"),
        ("mes_fatura", "TEXT"),
        ("parcela_atual", "INTEGER DEFAULT 1"),
        ("total_parcelas", "INTEGER DEFAULT 1"),
        ("pago", "INTEGER DEFAULT 0"),
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
      "Moradia & Contas",
      "Financiamento/Dívida",
      "Transporte & Veículo",
      "Alimentação",
      "Lazer & Compras",
      "Saúde",
      "Outros",
  ]
  metodos_disponiveis = [
      "Cartão de Crédito",
      "Boleto",
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
data_compra = date.today()
mes_fatura_alvo = date.today().strftime("%Y-%m")

if tipo_mov == "Despesa":
  st.sidebar.markdown("📅 **Data & Vencimento**")
  data_compra = st.sidebar.date_input(
      "Data da Compra / Registo", value=date.today(), key="sb_dt_compra"
  )

  if metodo_mov == "Cartão de Crédito":
    mes_fatura_alvo = st.sidebar.text_input(
        "Mês da Fatura de Destino (AAAA-MM)",
        value=data_compra.strftime("%Y-%m"),
        key="sb_mes_fat_alvo",
        help="Ex: 2026-10 para fatura de Outubro, 2026-11 para Novembro",
    )
    num_parcelas = st.sidebar.number_input(
        "Quantidade de Prestações",
        min_value=1,
        max_value=48,
        value=1,
        step=1,
        key="sb_num_parc_card",
    )
  elif cat_mov == "Financiamento/Dívida":
    num_parcelas = st.sidebar.number_input(
        "Quantidade de Prestações",
        min_value=1,
        max_value=360,
        value=12,
        step=1,
        key="sb_num_parc_fin",
    )

with st.sidebar.form("form_novo_lancamento", clear_on_submit=True):
  desc_mov = st.text_input(
      "Descrição", placeholder="Ex: Fatura Mercado Pago, Celular, Supermercado"
  )
  ciclo_mov = st.selectbox(
      "Vencimento / Ciclo", ["Dia 20", "Dia 05", "Outro Momento"]
  )
  tipo_valor = st.radio(
      "O valor informado abaixo é:",
      ["Valor da Parcela Mensal", "Valor Total da Compra"],
      index=0 if (cat_mov == "Financiamento/Dívida" and num_parcelas > 1) else 1,
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

        # 1. Cartão de Crédito
        if tipo_mov == "Despesa" and metodo_mov == "Cartão de Crédito":
          val_parcela = (
              valor_input / num_parcelas
              if tipo_valor == "Valor Total da Compra"
              else valor_input
          )
          try:
            dt_base_fat = datetime.strptime(
                mes_fatura_alvo.strip(), "%Y-%m"
            ).date()
          except Exception:
            dt_base_fat = data_compra

          for i in range(int(num_parcelas)):
            dt_fat = dt_base_fat + relativedelta(months=i)
            fat_str = dt_fat.strftime("%Y-%m")
            desc_parcelada = (
                f"{desc_mov.strip()} ({i + 1}/{num_parcelas})"
                if num_parcelas > 1
                else desc_mov.strip()
            )
            # Todo lançamento entra como 0 (Pendente)
            c.execute(
                """
                            INSERT INTO transacoes (usuario_id, data, descricao, tipo, categoria, metodo, ciclo, valor, mes_fatura, parcela_atual, total_parcelas, pago)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
                        """,
                (
                    USER_ID,
                    str(data_compra),
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

        # 2. Financiamento/Dívida parcelado
        elif (
            tipo_mov == "Despesa"
            and num_parcelas > 1
            and cat_mov == "Financiamento/Dívida"
        ):
          val_parcela = (
              valor_input
              if tipo_valor == "Valor da Parcela Mensal"
              else (valor_input / num_parcelas)
          )
          dia_v = data_compra.day

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
                  str(data_compra),
              ),
          )

          for i in range(int(num_parcelas)):
            dt_parcela = data_compra + relativedelta(months=i)
            fat_str = dt_parcela.strftime("%Y-%m")
            desc_parcelada = f"{desc_mov.strip()} ({i + 1}/{num_parcelas})"
            c.execute(
                """
                            INSERT INTO transacoes (usuario_id, data, descricao, tipo, categoria, metodo, ciclo, valor, mes_fatura, parcela_atual, total_parcelas, pago)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 0)
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

        # 3. Lançamento Comum (à vista)
        else:
          c.execute(
              """
                        INSERT INTO transacoes (usuario_id, data, descricao, tipo, categoria, metodo, ciclo, valor, mes_fatura, parcela_atual, total_parcelas, pago)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1, 0)
                    """,
              (
                  USER_ID,
                  str(data_compra),
                  desc_mov.strip(),
                  tipo_mov,
                  cat_mov,
                  metodo_mov,
                  ciclo_mov,
                  valor_input,
                  None,
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

# Mapeia todos os meses relevantes
meses_set = set([date.today().strftime("%Y-%m")])
if not df_trans.empty:
  for m in df_trans["mes_ano"].dropna():
    meses_set.add(m)
  for m in df_trans["mes_fatura"].dropna():
    meses_set.add(m)

if not df_parcelas.empty:
  for _, p_row in df_parcelas.iterrows():
    if "data_inicio" in p_row and p_row["data_inicio"]:
      try:
        dt_ini = datetime.strptime(str(p_row["data_inicio"]), "%Y-%m-%d").date()
        tot = int(p_row["total_parcelas"])
        pag = int(p_row["parcelas_pagas"])
        rest = tot - pag
        for k in range(rest):
          meses_set.add((dt_ini + relativedelta(months=k)).strftime("%Y-%m"))
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

# 1. VISÃO GERAL DO MÊS (CONTROLO RIGOROSO DE PAGAMENTOS)
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

  # B) Financiamento do Mês
  itens_financiamento_mes = []
  total_financiamentos_mes = 0.0

  if not df_trans.empty:
    filtro_fin = (
        (df_trans["mes_ano"] == mes_selecionado)
        & (df_trans["tipo"] == "Despesa")
        & (
            df_trans["categoria"].str.contains("Financiamento", case=False, na=False)
            | df_trans["descricao"].str.contains("Financiamento", case=False, na=False)
        )
    )
    df_fin_trans = df_trans[filtro_fin].copy()
    for _, r in df_fin_trans.iterrows():
      itens_financiamento_mes.append({
          "id": r["id"],
          "data": r["data"],
          "descricao": r["descricao"],
          "categoria": r["categoria"],
          "metodo": r["metodo"],
          "parcela_atual": r["parcela_atual"],
          "total_parcelas": r["total_parcelas"],
          "valor": float(r["valor"]),
          "pago": int(r["pago"]) if "pago" in r else 0,
      })
      total_financiamentos_mes += float(r["valor"])

  if total_financiamentos_mes == 0.0 and not df_parcelas.empty:
    for _, p_row in df_parcelas.iterrows():
      tot = int(p_row["total_parcelas"])
      pag = int(p_row["parcelas_pagas"])
      rest = tot - pag
      if rest > 0:
        dt_ini_str = (
            p_row["data_inicio"]
            if "data_inicio" in p_row and p_row["data_inicio"]
            else None
        )
        try:
          dt_ini = (
              datetime.strptime(str(dt_ini_str), "%Y-%m-%d").date()
              if dt_ini_str
              else date.today()
          )
        except Exception:
          dt_ini = date.today()

        for step in range(rest):
          dt_venc_parc = dt_ini + relativedelta(months=step)
          if dt_venc_parc.strftime("%Y-%m") == mes_selecionado:
            num_p_atual = pag + step + 1
            val_p = float(p_row["valor_parcela"])
            total_financiamentos_mes += val_p
            itens_financiamento_mes.append({
                "id": f"P-{p_row['id']}",
                "data": str(dt_venc_parc),
                "descricao": f"{p_row['titulo']} ({num_p_atual}/{tot})",
                "categoria": "Financiamento/Dívida",
                "metodo": "Boleto",
                "parcela_atual": num_p_atual,
                "total_parcelas": tot,
                "valor": val_p,
                "pago": 0,
            })

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

  # Cálculo de Pagos e Pendentes
  total_pago_mes = 0.0
  if not df_cartao_mes.empty and "pago" in df_cartao_mes:
    total_pago_mes += df_cartao_mes[df_cartao_mes["pago"] == 1]["valor"].sum()
  if not df_outros_mes.empty and "pago" in df_outros_mes:
    total_pago_mes += df_outros_mes[df_outros_mes["pago"] == 1]["valor"].sum()
  for fin_i in itens_financiamento_mes:
    if fin_i.get("pago") == 1:
      total_pago_mes += fin_i["valor"]

  pendente_mes = max(total_gastos_mes - total_pago_mes, 0.0)

  # Cards de Métricas
  c1, c2, c3, c4 = st.columns(4)
  c1.metric("💳 Fatura do Cartão", f"R$ {total_cartao_mes:,.2f}")
  c2.metric("🚗 Parcela Financiamento", f"R$ {total_financiamentos_mes:,.2f}")
  c3.metric(
      "✅ Já Pago no Mês",
      f"R$ {total_pago_mes:,.2f}",
      delta=f"R$ {total_pago_mes:,.2f}",
      delta_color="normal",
  )
  c4.metric(
      f"⏳ Pendente a Pagar ({mes_selecionado})",
      f"R$ {pendente_mes:,.2f}",
      delta=(
          f"R$ -{pendente_mes:,.2f}"
          if pendente_mes > 0
          else "100% Liquidado"
      ),
      delta_color="inverse",
  )

  st.divider()

  col_det1, col_det2 = st.columns(2)

  with col_det1:
    st.write(f"##### 💳 Detalhes da Fatura do Cartão ({mes_selecionado})")
    if not df_cartao_mes.empty:
      for _, c_row in df_cartao_mes.iterrows():
        id_t = c_row["id"]
        esta_pago = bool(c_row["pago"] == 1) if "pago" in c_row else False
        col_c_txt, col_c_chk = st.columns([3.5, 1.5])
        with col_c_txt:
          badge = "🟢 Pago" if esta_pago else "🟡 Pendente"
          st.markdown(
              f"**{c_row['descricao']}** ({badge})  \n"
              f"<small style='color:#94a3b8;'>Data: {c_row['data']} • R$"
              f" {c_row['valor']:,.2f}</small>",
              unsafe_allow_html=True,
          )
        with col_c_chk:
          if st.button(
              "Marcar Pago" if not esta_pago else "Desmarcar",
              key=f"btn_pago_c_{id_t}",
              use_container_width=True,
          ):
            with get_db() as conn:
              c = conn.cursor()
              c.execute(
                  "UPDATE transacoes SET pago = ? WHERE id = ? AND usuario_id ="
                  " ?",
                  (0 if esta_pago else 1, id_t, USER_ID),
              )
              conn.commit()
            st.rerun()
    else:
      st.info("Nenhuma fatura de cartão prevista para este mês.")

  with col_det2:
    st.write(
        f"##### 🚗 Parcelas de Financiamentos & Boletos ({mes_selecionado})"
    )
    lista_comprovantes = []
    if itens_financiamento_mes:
      lista_comprovantes.extend(itens_financiamento_mes)
    if not df_outros_mes.empty:
      for _, o_row in df_outros_mes.iterrows():
        lista_comprovantes.append({
            "id": o_row["id"],
            "data": o_row["data"],
            "descricao": o_row["descricao"],
            "categoria": o_row["categoria"],
            "metodo": o_row["metodo"],
            "parcela_atual": o_row["parcela_atual"],
            "total_parcelas": o_row["total_parcelas"],
            "valor": float(o_row["valor"]),
            "pago": int(o_row["pago"]) if "pago" in o_row else 0,
        })

    if lista_comprovantes:
      for item_c in lista_comprovantes:
        item_id = item_c["id"]
        esta_pago_b = bool(item_c.get("pago") == 1)
        col_b_txt, col_b_chk = st.columns([3.5, 1.5])
        with col_b_txt:
          badge_b = "🟢 Pago" if esta_pago_b else "🟡 Pendente"
          st.markdown(
              f"**{item_c['descricao']}** ({badge_b})  \n"
              f"<small style='color:#94a3b8;'>Vencimento: {item_c['data']} • R$"
              f" {item_c['valor']:,.2f}</small>",
              unsafe_allow_html=True,
          )
        with col_b_chk:
          if isinstance(item_id, int):
            if st.button(
                "Marcar Pago" if not esta_pago_b else "Desmarcar",
                key=f"btn_pago_b_{item_id}",
                use_container_width=True,
            ):
              with get_db() as conn:
                c = conn.cursor()
                c.execute(
                    "UPDATE transacoes SET pago = ? WHERE id = ? AND usuario_id"
                    " = ?",
                    (0 if esta_pago_b else 1, item_id, USER_ID),
                )
                conn.commit()
              st.rerun()
          else:
            st.caption("Contrato fixo")
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

  itens_ciclo_todos = []
  if not df_trans.empty:
    df_ciclos_mes = df_trans[
        (
            (df_trans["mes_ano"] == mes_ciclo_sel)
            | (df_trans["mes_fatura"] == mes_ciclo_sel)
        )
        & (df_trans["tipo"] == "Despesa")
    ].copy()
    for _, tr in df_ciclos_mes.iterrows():
      pago_status = "🟢 Pago" if tr.get("pago") == 1 else "🟡 Pendente"
      itens_ciclo_todos.append({
          "id": tr["id"],
          "data": tr["data"],
          "descricao": tr["descricao"],
          "metodo": tr["metodo"],
          "categoria": tr["categoria"],
          "ciclo": tr["ciclo"],
          "valor": float(tr["valor"]),
          "status": pago_status,
      })

  if not df_parcelas.empty:
    for _, p_row in df_parcelas.iterrows():
      tot = int(p_row["total_parcelas"])
      pag = int(p_row["parcelas_pagas"])
      rest = tot - pag
      if rest > 0:
        dt_ini_str = (
            p_row["data_inicio"]
            if "data_inicio" in p_row and p_row["data_inicio"]
            else None
        )
        try:
          dt_ini = (
              datetime.strptime(str(dt_ini_str), "%Y-%m-%d").date()
              if dt_ini_str
              else date.today()
          )
        except Exception:
          dt_ini = date.today()

        for step in range(rest):
          dt_parc_v = dt_ini + relativedelta(months=step)
          if dt_parc_v.strftime("%Y-%m") == mes_ciclo_sel:
            ja_existe = any(
                p_row["titulo"].lower() in str(x["descricao"]).lower()
                for x in itens_ciclo_todos
            )
            if not ja_existe:
              dia_venc = int(p_row["dia_vencimento"])
              ciclo_calc = (
                  f"Dia {dia_venc:02d}"
                  if dia_venc in [5, 20]
                  else "Outro Momento"
              )
              itens_ciclo_todos.append({
                  "id": f"P-{p_row['id']}",
                  "data": str(dt_parc_v),
                  "descricao": f"{p_row['titulo']} ({pag + step + 1}/{tot})",
                  "metodo": "Boleto",
                  "categoria": "Financiamento/Dívida",
                  "ciclo": ciclo_calc,
                  "valor": float(p_row["valor_parcela"]),
                  "status": "🟡 Pendente",
              })

  if itens_ciclo_todos:
    df_ciclos_consolidado = pd.DataFrame(itens_ciclo_todos)
    col5, col20 = st.columns(2)

    with col5:
      st.markdown(
          f"<div class='card-ciclo'><h4>🗓️ Contas do Dia 05"
          f" ({mes_ciclo_sel})</h4></div>",
          unsafe_allow_html=True,
      )
      df_5 = df_ciclos_consolidado[
          df_ciclos_consolidado["ciclo"] == "Dia 05"
      ].copy()
      st.metric(f"Total no Dia 5 ({mes_ciclo_sel})", f"R$ {df_5['valor'].sum():,.2f}")
      if not df_5.empty:
        df_5_tab = df_5[[
            "id",
            "data",
            "descricao",
            "metodo",
            "categoria",
            "status",
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
      df_20 = df_ciclos_consolidado[
          df_ciclos_consolidado["ciclo"] == "Dia 20"
      ].copy()
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
            "status",
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

    df_fat_view = df_card[df_card["mes_fatura"] == fat_sel].copy()
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
          "Data da Próxima Cobrança / Início", value=date.today()
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
            conn.commit()
          st.success("Financiamento guardado com sucesso!")
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
    st.info("Nenhum contrato ativo listado.")

# 5. GERENCIAR, EDITAR E EXCLUIR
with tab_gestao:
  st.subheader("⚙️ Painel de Edição e Eliminação Agrupado")

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
            "mes_fatura",
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
                "Moradia & Contas",
                "Financiamento/Dívida",
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
                "Financiamento/Dívida",
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
                "Cartão de Crédito",
                "Boleto",
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

            val_mes_fat = (
                reg_avulso["mes_fatura"]
                if reg_avulso["mes_fatura"]
                else ed_data.strftime("%Y-%m")
            )
            ed_mes_fat = st.text_input(
                "Mês da Fatura (AAAA-MM, ex: 2026-10)", value=val_mes_fat
            )

            lista_ciclo = ["Dia 20", "Dia 05", "Outro Momento"]
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
              fat_gravar = (
                  ed_mes_fat.strip()
                  if ed_met == "Cartão de Crédito"
                  else reg_avulso["mes_fatura"]
              )
              with get_db() as conn:
                c = conn.cursor()
                c.execute(
                    """
                                    UPDATE transacoes 
                                    SET descricao = ?, data = ?, tipo = ?, categoria = ?, metodo = ?, ciclo = ?, valor = ?, mes_fatura = ?
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
                        fat_gravar,
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