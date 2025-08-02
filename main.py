import streamlit as st
import pandas as pd
from datetime import datetime

st.set_page_config(layout="wide")


st.title("Análise de Reservas")

# 1. Upload do ficheiro
ficheiro = st.file_uploader("Carregar o ficheiro de reservas", type=["xls", "xlsx"])

# 2. Número de meses a analisar
n_meses_analisar = st.number_input(
    "Número de meses a analisar", min_value=2, max_value=6, value=3, step=1
)

if ficheiro:
    # 3. Leitura do ficheiro
    df = pd.read_excel(ficheiro, skiprows=17)
    colunas_a_manter = ['Dt. Criação', 'CNP', 'Produto', 'Qtd. Res.', 'Faturada']
    df = df[colunas_a_manter]
    df['Dt. Criação'] = pd.to_datetime(df['Dt. Criação'])
    
    
    # Novo filtro para Faturada
    filtro_faturada = st.selectbox(
        "Filtrar por Faturada:",
        options=["Todos", "Sim", "Não"],
        index=0
    )
    
    
    # Atualizar título com base no filtro
    if filtro_faturada == "Todos":
        st.subheader("Relatório: Todas as Reservas")
    elif filtro_faturada == "Sim":
        st.subheader("Relatório: Apenas Reservas Faturadas")
    else:
        st.subheader("Relatório: Apenas Reservas Não Faturadas")
    
    
    
    # Aplicar o Filtrp
    if filtro_faturada != "Todos":
        df = df[df['Faturada'] == filtro_faturada]

    # 4. Agrupar reservas por data, CNP e produto
    df_reservations = df.groupby(['Dt. Criação', 'CNP', 'Produto'])['Qtd. Res.'].sum().reset_index()

    # 5. Filtrar últimos n meses
    today = datetime.now()
    start_date = (today.replace(day=1) - pd.DateOffset(months=n_meses_analisar)).replace(day=1)
    df_filtered = df_reservations[df_reservations['Dt. Criação'] >= start_date].copy()

    # 6. Criar coluna AnoMes
    df_filtered['AnoMes'] = df_filtered['Dt. Criação'].dt.to_period('M')

    # 7. Agregação mensal
    report_data = df_filtered.groupby(['CNP', 'Produto', 'AnoMes']).agg(
        N_reservas=('Qtd. Res.', 'size'),
        Total_reservado=('Qtd. Res.', 'sum'),
    ).reset_index()

    # 8. Criar tabela pivot
    report_pivot = report_data.pivot_table(
        index=['CNP', 'Produto'],
        columns='AnoMes',
        values=['N_reservas', 'Total_reservado'],
        aggfunc='sum',
        fill_value=0
    )

    # 9. Ordenar meses
    sorted_months = sorted(report_pivot.columns.levels[1])
    report_pivot = report_pivot.reindex(columns=sorted_months, level=1)

    # 10. Renomear níveis
    report_pivot.columns = report_pivot.columns.set_names(['Métrica', 'Mês'])

    # 11. Adicionar totais
    report_pivot[('Total', 'N_reservas')] = report_pivot['N_reservas'].sum(axis=1)
    report_pivot[('Total', 'Total_reservado')] = report_pivot['Total_reservado'].sum(axis=1)

    # 12. Determinar limites dinâmicos para slider
    min_valor = int(report_pivot[('Total', 'N_reservas')].min())
    max_valor = int(report_pivot[('Total', 'N_reservas')].max())

    # Garantir que há pelo menos um intervalo válido
    if min_valor == max_valor:
        max_valor = min_valor + 1

    valor_minimo, valor_maximo = st.slider(
        "Intervalo de Total Reservado",
        min_value=min_valor,
        max_value=max_valor,
        value=(min_valor, max_valor)
    )

    # 13. Filtrar de acordo com o slider
    report_pivot = report_pivot[
        (report_pivot[('Total', 'N_reservas')] >= valor_minimo) &
        (report_pivot[('Total', 'N_reservas')] <= valor_maximo)
    ]

    
    # 14. Ordenar pela coluna Total - N_reservas de forma descendente
    report_pivot = report_pivot.sort_values(by=('Total', 'N_reservas'), ascending=False)
    
    
    #Função para aplicar cores às colunas por grupo
    def color_by_group(df):
        styles = pd.DataFrame('', index=df.index, columns=df.columns)
        for col in df.columns:
            if col[0] == 'N_reservas':
                styles[col] = 'background-color: rgba(206, 76, 143, 0.8);'  # rosa claro
            elif col[0] == 'Total_reservado':
                styles[col] = 'background-color: rgba(113, 185, 104, 0.8);'  # verde claro
            elif col[0] == 'Total':
                styles[col] = 'background-color: rgba(241, 196, 15, 0.15);'  # amarelo claro
        return styles

    
    # Aplicar o estilo
    styled_df = report_pivot.style.apply(color_by_group, axis=None)
    
    
    
    
    
    # 15. Mostrar dataframe
    st.dataframe(styled_df, use_container_width=True)
else:
    st.info("Por favor, carregue um ficheiro Excel para visualizar os dados.")
