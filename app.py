import io
import sqlite3
from datetime import date
import pandas as pd
import streamlit as st

DB_NAME = "financas.db"


# --- Banco de Dados ---
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
            metodo TEXT NOT NULL DEFAULT 'Pix',
            valor REAL NOT NULL
        )
    """)
  # Adiciona a coluna metodo caso o banco ja existisse na versao anterior
  try:
    c.execute(
        "ALTER TABLE transacoes ADD COLUMN metodo TEXT NOT NULL DEFAULT 'Pix'"
    )
  except sqlite3.OperationalError:
    pass

  # Tabela para metas mensais de despesa
  c.execute("""
        CREATE TABLE IF NOT EXISTS metas (
            mes_ano TEXT PRIMARY KEY,
            valor_meta REAL NOT NULL
        )
    """)
  conn.commit()
  conn.close()


def adicionar_transacao(data_reg, descricao, tipo, categoria, metodo, valor):
  conn = sqlite3.connect(DB_NAME)
  c = conn.cursor()
  c.execute(
      """
        INSERT INTO transacoes (data, descricao, tipo, categoria, metodo, valor)
        VALUES (?, ?, ?, ?, ?, ?)
    """,
      (data_reg, descricao, tipo, categoria, metodo, valor),
  )
  conn.commit()
  conn.close()


def remover_transacao(id_transacao):
  conn = sqlite3.connect(DB_NAME)
  c = conn.cursor()
  c.execute("DELETE FROM transacoes WHERE id = ?", (id_transacao,))
  conn.commit()
  conn.close()


def carregar_transacoes():
  conn = sqlite3.connect(DB_NAME)
  df = pd.read_sql_query(
      "SELECT * FROM transacoes ORDER BY data DESC, id DESC",
      conn,
      parse_dates=["data"],
  )
  conn.close()
  return df


def salvar_meta(mes_ano, valor_meta):
  conn = sqlite3.connect(DB_NAME)
  c = conn.cursor()
  c.execute(
      """
        INSERT INTO metas (mes_ano, valor_meta) VALUES (?, ?)
        ON CONFLICT(mes_ano) DO UPDATE SET valor_meta = excluded.valor_meta
    """,
      (mes_ano, valor_meta),
  )
  conn.commit()
  conn.close()


def obter_meta(mes_ano):
  conn = sqlite3.connect(DB_NAME)
  c = conn.cursor()
  c.execute("SELECT valor_meta FROM metas WHERE mes_ano = ?", (mes_ano,))
  row = c.fetchone()
  conn.close()
  return row[0] if row else 0.0


# --- Configuração da Página ---
st.set_page_config(
    page_title="Controle Financeiro Pro", layout="wide", page_icon="💰"
)
init_db()

st.title("💼 Gerenciador Financeiro Pessoal")

# --- Barra Lateral: Lançamento de Transação ---
st.sidebar.header("➕ Nova Transação")
with st.sidebar.form("form_transacao", clear_on_submit=True):
  data_reg = st.date_input("Data", value=date.today())
  descricao = st.text_input(
      "Descrição", placeholder="Ex: Supermercado, Aluguel, Salário"
  )
  tipo = st.selectbox("Tipo", ["Despesa", "Receita"])

  if tipo == "Despesa":
    categorias = [
        "Alimentação",
        "Moradia & Contas",
        "Transporte",
        "Lazer",
        "Educação",
        "Saúde",
        "Compras",
        "Outros",
    ]
  else:
    categorias = ["Salário", "Serviços / Extra", "Investimentos", "Outros"]

  categoria = st.selectbox("Categoria", categorias)
  metodo = st.selectbox(
      "Forma de Pagamento",
      [
          "Pix",
          "Cartão de Crédito",
          "Cartão de Débito",
          "Dinheiro",
          "Transferência / TED",
          "Boleto",
      ],
  )
  valor = st.number_input("Valor (R$)", min_value=0.01, format="%.2f", step=10.0)

  submit = st.form_submit_button("Salvar Registro")
  if submit:
    if descricao.strip():
      adicionar_transacao(
          str(data_reg), descricao.strip(), tipo, categoria, metodo, valor
      )
      st.sidebar.success("Transação registrada com sucesso!")
      st.rerun()
    else:
      st.sidebar.error("Informe uma descrição válida.")

# --- Barra Lateral: Filtros de Visualização ---
st.sidebar.divider()
st.sidebar.header("🔍 Filtros")

df_geral = carregar_transacoes()

if not df_geral.empty:
  df_geral["mes_ano"] = df_geral["data"].dt.strftime("%Y-%m")
  meses_disponiveis = sorted(df_geral["mes_ano"].unique(), reverse=True)

  mes_selecionado = st.sidebar.selectbox(
      "Selecione o Mês:", ["Todos os Meses"] + list(meses_disponiveis)
  )

  if mes_selecionado != "Todos os Meses":
    df_filtrado = df_geral[df_geral["mes_ano"] == mes_selecionado].copy()
  else:
    df_filtrado = df_geral.copy()
else:
  df_filtrado = pd.DataFrame()
  mes_selecionado = "Todos os Meses"

# --- Barra Lateral: Meta do Mês Atual ---
if mes_selecionado != "Todos os Meses":
  st.sidebar.divider()
  st.sidebar.header(f"🎯 Meta de Gastos ({mes_selecionado})")
  meta_atual = obter_meta(mes_selecionado)
  nova_meta = st.sidebar.number_input(
      "Definir Teto de Gastos (R$):",
      min_value=0.0,
      value=float(meta_atual),
      step=100.0,
  )
  if st.sidebar.button("Atualizar Meta"):
    salvar_meta(mes_selecionado, nova_meta)
    st.sidebar.success("Meta atualizada!")
    st.rerun()

# --- Painel Principal ---
if not df_filtrado.empty:
  receitas = df_filtrado[df_filtrado["tipo"] == "Receita"]["valor"].sum()
  despesas = df_filtrado[df_filtrado["tipo"] == "Despesa"]["valor"].sum()
  saldo = receitas - despesas

  # Métricas Principais
  col1, col2, col3 = st.columns(3)
  col1.metric("Receitas", f"R$ {receitas:,.2f}")
  col2.metric("Despesas", f"R$ {despesas:,.2f}")
  col3.metric(
      "Saldo no Período",
      f"R$ {saldo:,.2f}",
      delta=f"R$ {saldo:,.2f}",
      delta_color="normal",
  )

  # Monitor de Meta (se houver meta configurada para o mês)
  if mes_selecionado != "Todos os Meses":
    meta_definida = obter_meta(mes_selecionado)
    if meta_definida > 0:
      st.markdown("#### Progresso do Teto de Gastos")
      porcentagem = min(despesas / meta_definida, 1.0)
      st.progress(porcentagem)
      col_m1, col_m2 = st.columns(2)
      col_m1.write(
          f"**Gasto:** R$ {despesas:,.2f} de **R$ {meta_definida:,.2f}**"
      )
      if despesas > meta_definida:
        col_m2.error(f"⚠️ Atenção! Limite estourado em R$ {despesas - meta_definida:,.2f}")
      else:
        col_m2.success(f"✅ Dentro do orçamento. Restam R$ {meta_definida - despesas:,.2f}")

  st.divider()

  # Gráficos
  g1, g2 = st.columns(2)
  df_desp = df_filtrado[df_filtrado["tipo"] == "Despesa"]

  with g1:
    st.subheader("Gastos por Categoria")
    if not df_desp.empty:
      por_categoria = df_desp.groupby("categoria")["valor"].sum()
      st.bar_chart(por_categoria)
    else:
      st.info("Nenhuma despesa registrada para exibir categorias.")

  with g2:
    st.subheader("Gastos por Forma de Pagamento")
    if not df_desp.empty:
      por_metodo = df_desp.groupby("metodo")["valor"].sum()
      st.bar_chart(por_metodo)
    else:
      st.info("Nenhuma despesa para exibir formas de pagamento.")

  st.divider()

  # Tabela e Exportação
  st.subheader("📋 Histórico e Gerenciamento de Transações")

  col_tab, col_acoes = st.columns([3, 1])

  with col_tab:
    df_exibicao = df_filtrado.copy()
    df_exibicao["data"] = df_exibicao["data"].dt.strftime("%d/%m/%Y")
    st.dataframe(
        df_exibicao[
            ["id", "data", "descricao", "tipo", "categoria", "metodo", "valor"]
        ],
        use_container_width=True,
        hide_index=True,
    )

  with col_acoes:
    st.markdown("##### 🗑️ Excluir Registro")
    ids_disponiveis = df_filtrado["id"].tolist()
    id_para_excluir = st.selectbox(
        "Selecione o ID para remover:", ids_disponiveis
    )
    if st.button("Excluir Lançamento", type="secondary"):
      remover_transacao(id_para_excluir)
      st.success(f"Registro #{id_para_excluir} removido!")
      st.rerun()

    st.markdown("##### 📥 Exportar")
    # Exportar para CSV
    csv_data = df_filtrado.to_csv(index=False, sep=";").encode("utf-8-sig")
    st.download_button(
        label="Baixar Planilha (CSV)",
        data=csv_data,
        file_name=f"financas_{mes_selecionado}.csv",
        mime="text/csv",
    )

else:
  st.info(
      "Nenhuma movimentação encontrada para o período selecionado. Use o"
      " formulário à esquerda para cadastrar."
  )
