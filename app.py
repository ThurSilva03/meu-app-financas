import hashlib
import sqlite3
from datetime import date
import pandas as pd
import streamlit as st

DB_NAME = "financas.db"


# --- Funções de Segurança e Base de Dados ---
def hash_password(password: str) -> str:
  return hashlib.sha256(password.encode("utf-8")).hexdigest()


def get_db_connection():
  conn = sqlite3.connect(DB_NAME)
  conn.row_factory = sqlite3.Row
  return conn


def init_db():
  conn = get_db_connection()
  c = conn.cursor()

  # 1. Utilizadores
  c.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            nome TEXT NOT NULL,
            password_hash TEXT NOT NULL
        )
    """)

  # 2. Transações
  c.execute("""
        CREATE TABLE IF NOT EXISTS transacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            usuario_id INTEGER DEFAULT 1,
            data TEXT NOT NULL,
            descricao TEXT NOT NULL,
            tipo TEXT NOT NULL,
            categoria TEXT NOT NULL,
            metodo TEXT NOT NULL DEFAULT 'Pix',
            ciclo TEXT DEFAULT 'Outro',
            valor REAL NOT NULL,
            mes_fatura TEXT
        )
    """)

  # 3. Garante atualização de colunas se o banco já existia
  colunas = [
      ("usuario_id", "INTEGER DEFAULT 1"),
      ("metodo", "TEXT NOT NULL DEFAULT 'Pix'"),
      ("ciclo", "TEXT DEFAULT 'Outro'"),
      ("mes_fatura", "TEXT"),
  ]
  for col, tipo_col in colunas:
    try:
      c.execute(f"ALTER TABLE transacoes ADD COLUMN {col} {tipo_col}")
    except sqlite3.OperationalError:
      pass

  # 4. Financiamentos e Parcelamentos
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
  conn.close()


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
        .block-container { padding-top: 1.8rem; padding-bottom: 3rem; }
        .stMetric {
            background: linear-gradient(135deg, rgba(30, 41, 59, 0.7), rgba(15, 23, 42, 0.8));
            border: 1px solid rgba(255, 255, 255, 0.08);
            border-radius: 12px;
            padding: 18px;
            box-shadow: 0 4px 15px rgba(0,0,0,0.25);
        }
        .fin-card {
            background-color: #1e293b;
            border-radius: 10px;
            padding: 20px;
            border-left: 5px solid #6366f1;
            margin-bottom: 12px;
            box-shadow: 0 2px 8px rgba(0,0,0,0.15);
        }
    </style>
""",
    unsafe_allow_html=True,
)

# --- Gestão de Sessão do Utilizador ---
if "user_id" not in st.session_state:
  st.session_state["user_id"] = None
if "user_nome" not in st.session_state:
  st.session_state["user_nome"] = None


# --- Ecrã de Login / Registo ---
def tela_autenticacao():
  st.markdown(
      "<h2 style='text-align: center; margin-bottom: 2rem;'>💼 Apex Finance •"
      " Portal de Acesso</h2>",
      unsafe_allow_html=True,
  )
  col1, col2, col3 = st.columns([1, 1.8, 1])

  with col2:
    tab_login, tab_cadastro = st.tabs(
        ["🔐 Iniciar Sessão", "📝 Criar Nova Conta"]
    )

    with tab_login:
      st.write("Introduza as suas credenciais para aceder aos seus dados.")
      u_login = st.text_input("Nome de utilizador", key="login_user")
      p_login = st.text_input(
          "Palavra-passe", type="password", key="login_pass"
      )

      if st.button("Entrar", type="primary", use_container_width=True):
        if u_login.strip() and p_login.strip():
          conn = get_db_connection()
          c = conn.cursor()
          c.execute(
              "SELECT id, nome, password_hash FROM usuarios WHERE username = ?",
              (u_login.strip().lower(),),
          )
          user = c.fetchone()
          conn.close()

          if user and user["password_hash"] == hash_password(p_login):
            st.session_state["user_id"] = user["id"]
            st.session_state["user_nome"] = user["nome"]
            st.rerun()
          else:
            st.error("Nome de utilizador ou palavra-passe incorretos.")
        else:
          st.warning("Preencha todos os campos.")

    with tab_cadastro:
      st.write("Registe um perfil isolado para gerir as suas despesas.")
      c_nome = st.text_input("O seu Nome", key="cad_nome")
      c_user = st.text_input(
          "Nome de Utilizador (ex: arthur)", key="cad_user"
      ).lower()
      c_pass = st.text_input(
          "Definir Palavra-passe", type="password", key="cad_pass"
      )

      if st.button("Criar Conta", use_container_width=True):
        if c_nome.strip() and c_user.strip() and c_pass.strip():
          conn = get_db_connection()
          c = conn.cursor()
          try:
            c.execute(
                """
                            INSERT INTO usuarios (username, nome, password_hash)
                            VALUES (?, ?, ?)
                        """,
                (c_user.strip(), c_nome.strip(), hash_password(c_pass)),
            )
            conn.commit()
            st.success("Conta criada com sucesso! Aceda ao separador Entrar.")
          except sqlite3.IntegrityError:
            st.error("Este nome de utilizador já existe. Escolha outro.")
          finally:
            conn.close()
        else:
          st.warning("Preencha todos os dados de registo.")


if not st.session_state["user_id"]:
  tela_autenticacao()
  st.stop()

# --- Painel Principal ---
USER_ID = st.session_state["user_id"]

st.sidebar.markdown(f"### Olá, **{st.session_state['user_nome']}** 👋")
if st.sidebar.button("Terminar Sessão", type="secondary"):
  st.session_state["user_id"] = None
  st.session_state["user_nome"] = None
  st.rerun()

st.sidebar.divider()
st.sidebar.header("➕ Lançamento Rápido")
with st.sidebar.form("form_transacao", clear_on_submit=True):
  data_reg = st.date_input("Data do Pagamento", value=date.today())
  desc = st.text_input("Descrição", placeholder="Ex: Combustível, Conta de Luz")
  tipo_t = st.selectbox("Tipo de Movimento", ["Despesa", "Receita"])

  if tipo_t == "Despesa":
    cats = [
        "Alimentação",
        "Habitação & Contas",
        "Transporte & Veículo",
        "Lazer & Subscrições",
        "Saúde",
        "Financiamento/Dívida",
        "Outros",
    ]
  else:
    cats = ["Salário Principal", "Adiantamento/Vale", "Rendimentos", "Outros"]

  categoria_t = st.selectbox("Categoria", cats)
  metodo_t = st.selectbox(
      "Método",
      [
          "Pix",
          "Cartão de Crédito",
          "Cartão de Débito",
          "Dinheiro",
          "Débito Direto",
      ],
  )
  ciclo_t = st.selectbox(
      "Ciclo de Pagamento / Vencimento",
      ["Dia 05", "Dia 20", "Outro Momento do Mês"],
  )

  fatura_t = None
  if metodo_t == "Cartão de Crédito":
    fatura_t = st.text_input(
        "Mês da Fatura (AAAA-MM)", value=date.today().strftime("%Y-%m")
    )

  valor_t = st.number_input(
      "Valor (R$)", min_value=0.01, format="%.2f", step=10.0
  )

  if st.form_submit_button("Registar Movimento", use_container_width=True):
    if desc.strip():
      conn = get_db_connection()
      c = conn.cursor()
      c.execute(
          """
                INSERT INTO transacoes (usuario_id, data, descricao, tipo, categoria, metodo, ciclo, valor, mes_fatura)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
          (
              USER_ID,
              str(data_reg),
              desc.strip(),
              tipo_t,
              categoria_t,
              metodo_t,
              ciclo_t,
              valor_t,
              fatura_t,
          ),
      )
      conn.commit()
      conn.close()
      st.sidebar.success("Lançamento guardado com sucesso!")
      st.rerun()

# Separadores de Navegação
tab_dash, tab_ciclos, tab_cartao, tab_parcelas = st.tabs([
    "📊 Visão Geral & Métricas",
    "🗓️ Organização Dia 5 / Dia 20",
    "💳 Faturas de Cartão",
    "🚗 Financiamentos & Parcelamentos",
])

conn = get_db_connection()
df_user = pd.read_sql_query(
    "SELECT * FROM transacoes WHERE usuario_id = ? ORDER BY data DESC",
    conn,
    params=(USER_ID,),
    parse_dates=["data"],
)
df_parcelas = pd.read_sql_query(
    "SELECT * FROM parcelamentos WHERE usuario_id = ?",
    conn,
    params=(USER_ID,),
)
conn.close()

# 1. Visão Geral
with tab_dash:
  st.subheader("Painel Geral de Finanças")
  if not df_user.empty:
    df_user["mes_ano"] = df_user["data"].dt.strftime("%Y-%m")
    mes_selecionado = st.selectbox(
        "Filtrar por Mês:",
        ["Todos os Períodos"] + sorted(df_user["mes_ano"].unique(), reverse=True),
    )

    df_view = (
        df_user[df_user["mes_ano"] == mes_selecionado]
        if mes_selecionado != "Todos os Períodos"
        else df_user
    )

    tot_rec = df_view[df_view["tipo"] == "Receita"]["valor"].sum()
    tot_desp = df_view[df_view["tipo"] == "Despesa"]["valor"].sum()
    saldo = tot_rec - tot_desp

    c1, c2, c3 = st.columns(3)
    c1.metric("Entradas no Período", f"R$ {tot_rec:,.2f}")
    c2.metric("Saídas no Período", f"R$ {tot_desp:,.2f}")
    c3.metric(
        "Balanço Restante",
        f"R$ {saldo:,.2f}",
        delta=f"R$ {saldo:,.2f}",
        delta_color="normal",
    )

    st.divider()
    col_g1, col_g2 = st.columns(2)
    with col_g1:
      st.write("##### Gastos por Categoria")
      despesas_cat = (
          df_view[df_view["tipo"] == "Despesa"]
          .groupby("categoria")["valor"]
          .sum()
      )
      if not despesas_cat.empty:
        st.bar_chart(despesas_cat)
      else:
        st.info("Sem despesas para demonstrar categorias.")

    with col_g2:
      st.write("##### Movimentações Recentes")
      st.dataframe(
          df_view[["data", "descricao", "categoria", "metodo", "valor"]],
          use_container_width=True,
          hide_index=True,
      )
  else:
    st.info("Ainda não tem transações registadas.")

# 2. Ciclos Dia 5 / Dia 20
with tab_ciclos:
  st.subheader("Planeamento e Separação de Vencimentos")
  if not df_user.empty:
    df_despesas = df_user[df_user["tipo"] == "Despesa"].copy()
    col_d5, col_d20 = st.columns(2)

    with col_d5:
      st.markdown(
          "<div class='fin-card'><h4>🗓️ Contas do Dia 05</h4><p>Compromissos"
          " do início do mês</p></div>",
          unsafe_allow_html=True,
      )
      df_5 = df_despesas[df_despesas["ciclo"] == "Dia 05"]
      tot_5 = df_5["valor"].sum()
      st.metric("Total no Dia 5", f"R$ {tot_5:,.2f}")
      if not df_5.empty:
        st.dataframe(
            df_5[["data", "descricao", "categoria", "valor"]],
            use_container_width=True,
            hide_index=True,
        )
      else:
        st.write("Sem contas registadas no Dia 5.")

    with col_d20:
      st.markdown(
          "<div class='fin-card'><h4>🗓️ Contas do Dia 20</h4><p>Compromissos"
          " do meio do mês</p></div>",
          unsafe_allow_html=True,
      )
      df_20 = df_despesas[df_despesas["ciclo"] == "Dia 20"]
      tot_20 = df_20["valor"].sum()
      st.metric("Total no Dia 20", f"R$ {tot_20:,.2f}")
      if not df_20.empty:
        st.dataframe(
            df_20[["data", "descricao", "categoria", "valor"]],
            use_container_width=True,
            hide_index=True,
        )
      else:
        st.write("Sem contas registadas no Dia 20.")
  else:
    st.info("Registe despesas para visualizar os ciclos.")

# 3. Faturas de Cartão
with tab_cartao:
  st.subheader("Controlo de Faturas de Cartão de Crédito")
  if not df_user.empty:
    df_cartao = df_user[df_user["metodo"] == "Cartão de Crédito"].copy()
    if not df_cartao.empty:
      faturas = sorted(df_cartao["mes_fatura"].dropna().unique(), reverse=True)
      fat_selecionada = st.selectbox("Selecione o Mês da Fatura:", faturas)

      df_fat = df_cartao[df_cartao["mes_fatura"] == fat_selecionada]
      st.metric(
          f"Total da Fatura ({fat_selecionada})", f"R$ {df_fat['valor'].sum():,.2f}"
      )
      st.dataframe(
          df_fat[["data", "descricao", "categoria", "valor"]],
          use_container_width=True,
          hide_index=True,
      )
    else:
      st.info("Nenhuma compra efetuada no Cartão de Crédito.")
  else:
    st.info("Sem transações registadas.")

# 4. Financiamentos e Parcelamentos
with tab_parcelas:
  st.subheader("Financiamentos e Despesas Parceladas")

  with st.expander("➕ Registar Novo Financiamento ou Parcela"):
    with st.form("form_novo_contrato"):
      f_titulo = st.text_input(
          "Descrição", placeholder="Ex: Financiamento Veículo, Smartphone"
      )
      f_tipo = st.selectbox(
          "Tipo", ["Financiamento Veículo", "Parcelamento Geral"]
      )
      col_p1, col_p2 = st.columns(2)
      f_total_p = col_p1.number_input(
          "Total de Parcelas", min_value=2, value=48, step=1
      )
      f_pagas_p = col_p2.number_input(
          "Parcelas Já Pagas", min_value=0, value=0, step=1
      )
      col_p3, col_p4 = st.columns(2)
      f_val_p = col_p3.number_input(
          "Valor da Parcela (R$)", min_value=0.01, value=850.0, step=10.0
      )
      f_dia_v = col_p4.selectbox(
          "Dia de Pagamento", [5, 20, 10, 15, 25, 30]
      )

      if st.form_submit_button("Guardar Contrato"):
        if f_titulo.strip():
          conn = get_db_connection()
          c = conn.cursor()
          c.execute(
              """
                        INSERT INTO parcelamentos (usuario_id, titulo, tipo_contrato, total_parcelas, parcelas_pagas, valor_parcela, dia_vencimento)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
              (
                  USER_ID,
                  f_titulo.strip(),
                  f_tipo,
                  f_total_p,
                  f_pagas_p,
                  f_val_p,
                  f_dia_v,
              ),
          )
          conn.commit()
          conn.close()
          st.success("Contrato registado com sucesso!")
          st.rerun()

  if not df_parcelas.empty:
    for _, row in df_parcelas.iterrows():
      cid = row["id"]
      restantes = row["total_parcelas"] - row["parcelas_pagas"]
      progresso = min(row["parcelas_pagas"] / row["total_parcelas"], 1.0)
      saldo_dev = restantes * row["valor_parcela"]

      st.markdown(f"#### 📌 {row['titulo']} ({row['tipo_contrato']})")
      c_i1, c_i2, c_i3 = st.columns(3)
      c_i1.metric(
          "Progresso", f"{row['parcelas_pagas']} de {row['total_parcelas']} pagas"
      )
      c_i2.metric("Valor da Parcela", f"R$ {row['valor_parcela']:,.2f}")
      c_i3.metric("Saldo Devedor", f"R$ {saldo_dev:,.2f}")

      st.progress(progresso)

      if restantes > 0:
        c_ciclo = (
            f"Dia {row['dia_vencimento']:02d}"
            if row["dia_vencimento"] in [5, 20]
            else "Outro Momento do Mês"
        )
        if st.button(
            f"Pagar Próxima Parcela (#{row['parcelas_pagas'] + 1})",
            key=f"p_{cid}",
            type="primary",
        ):
          conn = get_db_connection()
          c = conn.cursor()
          c.execute(
              "UPDATE parcelamentos SET parcelas_pagas = parcelas_pagas + 1"
              " WHERE id = ?",
              (cid,),
          )
          desc_auto = f"Parcela {row['parcelas_pagas'] + 1}/{row['total_parcelas']} - {row['titulo']}"
          c.execute(
              """
                        INSERT INTO transacoes (usuario_id, data, descricao, tipo, categoria, metodo, ciclo, valor)
                        VALUES (?, ?, ?, 'Despesa', 'Financiamento/Dívida', 'Débito Direto', ?, ?)
                    """,
              (
                  USER_ID,
                  str(date.today()),
                  desc_auto,
                  c_ciclo,
                  row["valor_parcela"],
              ),
          )
          conn.commit()
          conn.close()
          st.success("Parcela paga e registada no extrato!")
          st.rerun()
      else:
        st.success("🎉 Totalmente liquidado!")
      st.divider()
  else:
    st.info("Nenhum financiamento ou parcelamento ativo.")