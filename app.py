import sqlite3
from datetime import date
import pandas as pd
import streamlit as st

# --- Configuração do Banco de Dados SQLite ---
DB_NAME = "financas.db"


def init_db():
  conn = sqlite3.connect(DB_NAME)
  c = conn.cursor()
  c.execute("""
        CREATE TABLE IF NOT EXISTS transacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data TEXT NOT NULL,
            descricao TEXT NOT NULL,
            tipo TEXT NOT NULL,
            categoria TEXT NOT NULL,
            valor REAL NOT NULL
        )
    """)
  conn.commit()
  conn.close()


def adicionar_transacao(data_reg, descricao, tipo, categoria, valor):
  conn = sqlite3.connect(DB_NAME)
  c = conn.cursor()
  c.execute(
      """
        INSERT INTO transacoes (data, descricao, tipo, categoria, valor)
        VALUES (?, ?, ?, ?, ?)
    """,
      (data_reg, descricao, tipo, categoria, valor),
  )
  conn.commit()
  conn.close()


def carregar_transacoes():
  conn = sqlite3.connect(DB_NAME)
  df = pd.read_sql_query(
      "SELECT * FROM transacoes ORDER BY data DESC",
      conn,
      parse_dates=["data"],
  )
  conn.close()
  return df


# --- Interface Streamlit ---
st.set_page_config(
    page_title="Controle Financeiro", layout="wide", page_icon="💰"
)
init_db()

st.title("💼 Gerenciador de Finanças Pessoais")

# Barra Lateral: Registro de Transações
st.sidebar.header("Nova Transação")
with st.sidebar.form("form_transacao", clear_on_submit=True):
  data_reg = st.date_input("Data", value=date.today())
  descricao = st.text_input(
      "Descrição", placeholder="Ex: Mercado, Combustível, Salário"
  )
  tipo = st.selectbox("Tipo", ["Despesa", "Receita"])

  categorias = [
      "Alimentação",
      "Moradia & Contas",
      "Transporte",
      "Lazer",
      "Educação",
      "Saúde",
      "Outros",
  ]
  if tipo == "Receita":
    categorias = ["Salário", "Serviços / Extra", "Rendimentos", "Outros"]

  categoria = st.selectbox("Categoria", categorias)
  valor = st.number_input("Valor (R$)", min_value=0.01, format="%.2f", step=10.0)

  submit = st.form_submit_button("Adicionar Transação")
  if submit:
    if descricao.strip():
      adicionar_transacao(
          str(data_reg), descricao.strip(), tipo, categoria, valor
      )
      st.sidebar.success("Transação registrada com sucesso!")
    else:
      st.sidebar.error("Informe uma descrição válida.")

# Exibição de Dados e Métricas
df = carregar_transacoes()

if not df.empty:
  receitas = df[df["tipo"] == "Receita"]["valor"].sum()
  despesas = df[df["tipo"] == "Despesa"]["valor"].sum()
  saldo = receitas - despesas

  # Cards de Resumo
  col1, col2, col3 = st.columns(3)
  col1.metric("Receita Total", f"R$ {receitas:,.2f}")
  col2.metric("Despesa Total", f"R$ {despesas:,.2f}")
  col3.metric(
      "Saldo Atual",
      f"R$ {saldo:,.2f}",
      delta=f"R$ {saldo:,.2f}",
      delta_color="normal",
  )

  st.divider()

  # Gráficos e Tabela
  col_graf, col_tab = st.columns(2)

  with col_graf:
    st.subheader("Despesas por Categoria")
    df_despesas = df[df["tipo"] == "Despesa"]
    if not df_despesas.empty:
      gastos_cat = df_despesas.groupby("categoria")["valor"].sum()
      st.bar_chart(gastos_cat)
    else:
      st.info("Nenhuma despesa registrada para o gráfico.")

  with col_tab:
    st.subheader("Histórico de Transações")
    st.dataframe(
        df[["data", "descricao", "tipo", "categoria", "valor"]],
        use_container_width=True,
    )
else:
  st.info(
      "Nenhuma transação cadastrada ainda. Use o formulário na barra lateral"
      " para adicionar suas despesas ou receitas!"
  )