# --- Lançamento Rápido na Barra Lateral ---
st.sidebar.header("➕ Novo Registro")

# 1. Campos que controlam a lógica dinâmica (ficam fora do form para atualizar na hora)
tipo_mov = st.sidebar.selectbox("Tipo", ["Despesa", "Receita"], key="sidebar_tipo")

if tipo_mov == "Despesa":
    cats = [
        "Alimentação",
        "Moradia & Contas",
        "Transporte & Veículo",
        "Lazer & Compras",
        "Saúde",
        "Financiamento/Dívida",
        "Outros"
    ]
    metodos_disponiveis = ["Cartão de Crédito", "Pix", "Cartão de Débito", "Dinheiro", "Boleto"]
else:
    cats = ["Salário Principal", "Vale / Adiantamento", "Extra", "Outros"]
    metodos_disponiveis = ["Pix", "Transferência / TED", "Dinheiro", "Outro"]

metodo_mov = st.sidebar.selectbox("Forma de Pagamento", metodos_disponiveis, key="sidebar_metodo")

# 2. Formulário com os campos de detalhes
with st.sidebar.form("form_novo_lancamento", clear_on_submit=True):
    data_mov = st.date_input("Data", value=date.today())
    desc_mov = st.text_input("Descrição", placeholder="Ex: Supermercado, Smartphone")
    cat_mov = st.selectbox("Categoria", cats)
    ciclo_mov = st.selectbox("Vencimento / Ciclo", ["Dia 05", "Dia 20", "Outro Momento"])

    # Se for Cartão de Crédito, mostra os campos de parcelas instantaneamente:
    if tipo_mov == "Despesa" and metodo_mov == "Cartão de Crédito":
        st.markdown("💳 **Configuração de Parcelas**")
        num_parcelas = st.number_input("Quantidade de Parcelas", min_value=1, max_value=48, value=1, step=1)
        fatura_inicio = st.text_input("Mês da 1ª Fatura (AAAA-MM)", value=date.today().strftime("%Y-%m"))
    else:
        num_parcelas = 1
        fatura_inicio = date.today().strftime("%Y-%m")

    valor_mov = st.number_input("Valor Total da Compra (R$)", min_value=0.01, format="%.2f", step=10.0)

    salvar_btn = st.form_submit_button("Salvar Registro", use_container_width=True)

    if salvar_btn:
        if desc_mov.strip():
            with get_db() as conn:
                c = conn.cursor()
                if tipo_mov == "Despesa" and metodo_mov == "Cartão de Crédito" and num_parcelas > 1:
                    val_parcela = valor_mov / num_parcelas
                    try:
                        dt_base = datetime.strptime(fatura_inicio.strip(), "%Y-%m")
                    except Exception:
                        dt_base = datetime.now()

                    for i in range(int(num_parcelas)):
                        dt_fat = dt_base + relativedelta(months=i)
                        fat_str = dt_fat.strftime("%Y-%m")
                        desc_parcelada = f"{desc_mov.strip()} ({i + 1}/{num_parcelas})"
                        c.execute("""
                            INSERT INTO transacoes (usuario_id, data, descricao, tipo, categoria, metodo, ciclo, valor, mes_fatura, parcela_atual, total_parcelas)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (USER_ID, str(data_mov), desc_parcelada, tipo_mov, cat_mov, metodo_mov, ciclo_mov, val_parcela, fat_str, i + 1, num_parcelas))
                else:
                    fat_unica = fatura_inicio if metodo_mov == "Cartão de Crédito" else None
                    c.execute("""
                        INSERT INTO transacoes (usuario_id, data, descricao, tipo, categoria, metodo, ciclo, valor, mes_fatura, parcela_atual, total_parcelas)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, 1)
                    """, (USER_ID, str(data_mov), desc_mov.strip(), tipo_mov, cat_mov, metodo_mov, ciclo_mov, valor_mov, fat_unica))
                conn.commit()
            st.sidebar.success("Gravado com sucesso!")
            st.rerun()
        else:
            st.sidebar.error("Informe a descrição.")