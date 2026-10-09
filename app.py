from datetime import date, datetime
import hashlib
import sqlite3
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
                password_hash TEXT NOT NULL
            )
        """)

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

    # Atualizações de colunas se o banco já existia
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

# --- Configuração Visual ---
st.set_page_config(
    page_title="Apex Finance | Controle Pessoal",
    layout="wide",
    page_icon="💳",
    initial_sidebar_state="expanded",
)

st.markdown(
    """
    <style>
        .block-container { padding-top: 1.5rem; padding-bottom: 3rem; }
        .stMetric {
            background-color: #1e293b !important;
            border: 1px solid #334155;
            border-radius: 10px;
            padding: 15px;
        }
        .card-ciclo {
            background: #1e293b;
            padding: 16px;
            border-radius: 8px;
            border-left: 5px solid #38bdf8;
            margin-bottom: 12px;
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


# --- Autenticação ---
def tela_login():
  st.markdown(
      "<h2 style='text-align: center;'>💼 Apex Finance • Acesso Pessoal</h2>",
      unsafe_allow_html=True,
  )
  col1, col2, col3 = st.columns([1, 1.8, 1])

  with col2:
    tab_log, tab_cad = st.tabs(["🔐 Entrar", "📝 Criar Conta"])

    with tab_log:
      u_log = st.text_input("Usuário", key="txt_login_u")
      p_log = st.text_input("Senha", type="password", key="txt_login_p")
      if st.button("Acessar", type="primary", use_container_width=True):
        if u_log and p_log:
          with get_db() as conn:
            c = conn.cursor()
            c.execute(
                "SELECT id, nome, password_hash FROM usuarios WHERE username ="
                " ?",
                (u_log.strip().lower(),),
            )
            usuario = c.fetchone()
            if usuario and usuario["password_hash"] == hash_password(p_log):
              st.session_state["user_id"] = int(usuario["id"])
              st.session_state["user_nome"] = str(usuario["nome"])
              st.rerun()
            else:
              st.error("Usuário ou senha inválidos.")
        else:
          st.warning("Preencha todos os campos.")

    with tab_cad:
      c_nome = st.text_input("Seu Nome Completo", key="cad_nome")
      c_user = st.text_input(
          "Escolha um Usuário (ex: arthur)", key="cad_user"
      ).lower()
      c_pass = st.text_input("Escolha uma Senha", type="password", key="cad_p")
      if st.button("Cadastrar Perfil", use_container_width=True):
        if c_nome.strip() and c_user.strip() and c_pass.strip():
          try:
            with get_db() as conn:
              c = conn.cursor()
              c.execute(
                  """
                                INSERT INTO usuarios (username, nome, password_hash)
                                VALUES (?, ?, ?)
                            """,
                  (c_user.strip(), c_nome.strip(), hash_password(c_pass)),
              )
              conn.commit()
            st.success("Conta criada! Pode entrar pela aba Entrar.")
          except sqlite3.IntegrityError:
            st.error("Nome de usuário já em uso.")
        else:
          st.warning("Preencha todos os dados.")


if not st.session_state["user_id"]:
  tela_login()
  st.stop()

# --- Usuário Logado ---
USER_ID = st.session_state["user_id"]

st.sidebar.markdown(f"### Olá, **{st.session_state['user_nome']}** 👋")
if st.sidebar.button("Sair da Conta"):
  st.session_state["user_id"] = None
  st.session_state["user_nome"] = None
  st.rerun()

st.sidebar.divider()

# --- Lançamento Rápido na Barra Lateral ---
st.sidebar.header("➕ Novo Registro")
with st.sidebar.form("form_novo_lancamento", clear_on_submit=True):
  data_mov = st.date_input("Data", value=date.today())
  desc_mov = st.text_input("Descrição", placeholder="Ex: Supermercado, Salário")
  tipo_mov = st.selectbox("Tipo", ["Despesa", "Receita"])

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
  else:
    cats = ["Salário Principal", "Vale / Adiantamento", "Extra", "Outros"]

  cat_mov = st.selectbox("Categoria", cats)
  metodo_mov = st.selectbox(
      "Forma de Pagamento",
      ["Pix", "Cartão de Crédito", "Cartão de Débito", "Dinheiro", "Boleto"],
  )
  ciclo_mov = st.selectbox(
      "Vencimento / Ciclo", ["Dia 05", "Dia 20", "Outro Momento"]
  )

  num_parcelas = 1
  fatura_inicio = date.today().strftime("%Y-%m")
  if tipo_mov == "Despesa" and metodo_mov == "Cartão de Crédito":
    num_parcelas = st.number_input(
        "Quantidade de Parcelas", min_value=1, max_value=48, value=1, step=1
    )
    fatura_inicio = st.text_input(
        "Mês da 1ª Fatura (AAAA-MM)", value=date.today().strftime("%Y-%m")
    )

  valor_mov = st.number_input(
      "Valor Total (R$)", min_value=0.01, format="%.2f", step=10.0
  )

  salvar_btn = st.form_submit_button("Salvar Registro", use_container_width=True)

  if salvar_btn:
    if desc_mov.strip():
      with get_db() as conn:
        c = conn.cursor()
        if tipo_mov == "Despesa" and metodo_mov == "Cartão de Crédito":
          val_parcela = valor_mov / num_parcelas
          try:
            dt_base = datetime.strptime(fatura_inicio.strip(), "%Y-%m")
          except Exception:
            dt_base = datetime.now()

          for i in range(int(num_parcelas)):
            dt_fat = dt_base + relativedelta(months=i)
            fat_str = dt_fat.strftime("%Y-%m")
            desc_parcelada = f"{desc_mov.strip()} ({i + 1}/{num_parcelas})"
            c.execute(
                """
                            INSERT INTO transacoes (usuario_id, data, descricao, tipo, categoria, metodo, ciclo, valor, mes_fatura, parcela_atual, total_parcelas)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                (
                    USER_ID,
                    str(data_mov),
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
                  None,
              ),
          )
        conn.commit()
      st.sidebar.success("Gravado com sucesso!")
      st.rerun()
    else:
      st.sidebar.error("Informe a descrição.")

# --- Abas Principais ---
tab_dash, tab_ciclos, tab_cartao, tab_parcelas, tab_gestao = st.tabs([
    "📊 Visão Geral",
    "🗓️ Ciclos Dia 5 / Dia 20",
    "💳 Faturas do Cartão",
    "🚗 Financiamentos & Contratos",
    "⚙️ Editar / Excluir",
])

# Carregar dados do usuário
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

# 1. VISÃO GERAL
with tab_dash:
  st.subheader("Painel de Controle Financeiro")
  if not df_trans.empty:
    df_trans["data_dt"] = pd.to_datetime(df_trans["data"])
    df_trans["mes_ano"] = df_trans["data_dt"].dt.strftime("%Y-%m")

    meses = ["Todos os Meses"] + sorted(
        df_trans["mes_ano"].unique(), reverse=True
    )
    mes_filtro = st.selectbox("Selecione o Mês:", meses)

    df_view = (
        df_trans[df_trans["mes_ano"] == mes_filtro]
        if mes_filtro != "Todos os Meses"
        else df_trans
    )

    rec = df_view[df_view["tipo"] == "Receita"]["valor"].sum()
    desp = df_view[df_view["tipo"] == "Despesa"]["valor"].sum()
    balanco = rec - desp

    c1, c2, c3 = st.columns(3)
    c1.metric("Entradas", f"R$ {rec:,.2f}")
    c2.metric("Saídas", f"R$ {desp:,.2f}")
    c3.metric(
        "Saldo",
        f"R$ {balanco:,.2f}",
        delta=f"R$ {balanco:,.2f}",
        delta_color="normal",
    )

    st.divider()
    cg1, cg2 = st.columns([1, 1])
    with cg1:
      st.write("##### Gastos por Categoria")
      cat_gasto = (
          df_view[df_view["tipo"] == "Despesa"]
          .groupby("categoria")["valor"]
          .sum()
      )
      if not cat_gasto.empty:
        st.bar_chart(cat_gasto)
    with cg2:
      st.write("##### Últimos Lançamentos")
      st.dataframe(
          df_view[[
              "id",
              "data",
              "descricao",
              "tipo",
              "categoria",
              "metodo",
              "valor",
          ]],
          use_container_width=True,
          hide_index=True,
      )
  else:
    st.info("Nenhuma movimentação registrada. Use o menu à esquerda.")

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
      df_5 = df_d[df_d["ciclo"] == "Dia 05"]
      st.metric("Total no Dia 5", f"R$ {df_5['valor'].sum():,.2f}")
      if not df_5.empty:
        st.dataframe(
            df_5[["id", "data", "descricao", "categoria", "valor"]],
            use_container_width=True,
            hide_index=True,
        )
      else:
        st.write("Nenhuma conta associada ao Dia 5.")

    with col20:
      st.markdown(
          "<div class='card-ciclo'><h4>🗓️ Contas do Dia 20</h4></div>",
          unsafe_allow_html=True,
      )
      df_20 = df_d[df_d["ciclo"] == "Dia 20"]
      st.metric("Total no Dia 20", f"R$ {df_20['valor'].sum():,.2f}")
      if not df_20.empty:
        st.dataframe(
            df_20[["id", "data", "descricao", "categoria", "valor"]],
            use_container_width=True,
            hide_index=True,
        )
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
    st.dataframe(
        df_fat_view[[
            "id",
            "data",
            "descricao",
            "categoria",
            "parcela_atual",
            "total_parcelas",
            "valor",
        ]],
        use_container_width=True,
        hide_index=True,
    )
  else:
    st.info("Nenhuma compra no Cartão de Crédito lançada ainda.")

# 4. FINANCIAMENTOS E CONTRATOS FIXOS
with tab_parcelas:
  st.subheader("Financiamentos e Despesas Parceladas Fixas")

  with st.expander("➕ Cadastrar Novo Financiamento ou Parcela Fixa"):
    with st.form("form_cad_parcelamento"):
      c_tit = st.text_input(
          "Título do Contrato", placeholder="Ex: Financiamento Onix, Empréstimo"
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
  st.caption(
      "Selecione um lançamento ou contrato para corrigir dados incorretos ou"
      " apagar permanentemente."
  )

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
              "Pix",
              "Cartão de Crédito",
              "Cartão de Débito",
              "Dinheiro",
              "Boleto",
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
            f"Excluir o contrato **{parc_reg['titulo']}** não apagará as"
            " parcelas já pagas do seu histórico financeiro, apenas removerá o"
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