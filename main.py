import streamlit as st

import pandas as pd
from datetime import datetime



# Configurar página em wide mode
st.set_page_config(layout="wide")

# Título e descrição
# Colocar logo e título lado a lado
col_logo, col_title = st.columns([1, 5])

with col_logo:
    st.markdown(
        '<a href="https://pharmacoach.up.railway.app/about" target="_blank">'
        '<img src="https://raw.githubusercontent.com/foliveir84/public_images/main/Logo_Pharmacoach.jpg" width="150"></a>',
        unsafe_allow_html=True
    )

with col_title:
    st.title("💊 Reservas: Insights para Gestão de Portfólio e Stocks")
    st.write("""
Esta aplicação permite analisar todas as reservas efetuadas na farmácia, fornecendo indicadores que ajudam a otimizar a gestão do portfólio, os níveis de stock e a identificar oportunidades de melhoria.  
Através da análise de dados históricos, é possível distinguir produtos com maior procura, ajustar stocks mínimos e maximizar a eficiência operacional.
""")

# Créditos e Link do LinkedIn
st.markdown(
    """
    <div style="text-align:right">
        By <b>Filipe Oliveira</b>  
        <a href="https://www.linkedin.com/in/foliveir/" target="_blank">
            <img src="https://cdn-icons-png.flaticon.com/512/174/174857.png" width="20">
        </a>
    </div>
    """,
    unsafe_allow_html=True
)

# Vídeo tutorial sobre como exportar o ficheiro
with st.expander("📹 Ver tutorial de exportação do ficheiro"):
    st.video("https://www.youtube.com/embed/_qGgXx7HvUk")

# Ficheiro de upload
ficheiro = st.file_uploader("Carregar o ficheiro de reservas", type=["xlsx", ])

# Período de Análise
perido_analise = st.selectbox(
    "Período de Análise",
    options=[1, 2, 3, 4, 5, 6],
    index=2,  # Valor padrão de 3 meses
    help="Defina o intervalo de tempo para análise. O valor padrão é 3 meses para o passado, permitindo um olhar mais recente sobre os dados. Ajuste o período para uma visão mais ampla ou focada."
)

# Filtro Faturada
filtro_faturada = st.selectbox(
    "Filtrar por Faturada:",
    options=["Todos", "Sim", "Não"],
    index=0,
    help="Permite focar apenas em reservas faturadas, não faturadas, ou visualizar todas."
)

# Processamento de dados
if ficheiro:
    df = pd.read_excel(ficheiro, skiprows=17)
    colunas_a_manter = ['Dt. Criação', 'CNP', 'Produto', 'Qtd. Res.', 'Faturada']
    df = df[colunas_a_manter]
    df['Dt. Criação'] = pd.to_datetime(df['Dt. Criação'])

    # Aplicar filtro Faturada
    if filtro_faturada != "Todos":
        df = df[df['Faturada'] == filtro_faturada]

    # Agrupar dados
    df_reservations = df.groupby(['Dt. Criação', 'CNP', 'Produto'])['Qtd. Res.'].sum().reset_index()

    # Calcular a data de início para o filtro de meses
    today = datetime.now()
    start_date = (today.replace(day=1) - pd.DateOffset(months=perido_analise)).replace(day=1)
    df_filtered = df_reservations[df_reservations['Dt. Criação'] >= start_date].copy()

    df_filtered['AnoMes'] = df_filtered['Dt. Criação'].dt.to_period('M')

    report_data = df_filtered.groupby(['CNP', 'Produto', 'AnoMes']).agg(
        **{'Nº Pedidos de Reserva' : ('Qtd. Res.', 'size'),
        'Unidades Reservadas' : ('Qtd. Res.', 'sum')},
    ).reset_index()

    report_pivot = report_data.pivot_table(
        index=['CNP', 'Produto'],
        columns='AnoMes',
        values=['Nº Pedidos de Reserva', 'Unidades Reservadas'],
        aggfunc='sum',
        fill_value=0
    )

    # Reordenar meses
    sorted_months = sorted(report_pivot.columns.levels[1])
    report_pivot = report_pivot.reindex(columns=sorted_months, level=1)
    report_pivot.columns = report_pivot.columns.set_names(['Métrica', 'Mês'])

    # Cálculos totais
    report_pivot[('Total', 'Nº Pedidos de Reserva')] = report_pivot['Nº Pedidos de Reserva'].sum(axis=1)
    report_pivot[('Total', 'Unidades Reservadas')] = report_pivot['Unidades Reservadas'].sum(axis=1)

    # Slider para filtrar reservas
    min_valor = int(report_pivot[('Total', 'Nº Pedidos de Reserva')].min())
    max_valor = int(report_pivot[('Total', 'Nº Pedidos de Reserva')].max())

    if min_valor == max_valor:
        max_valor = min_valor + 1

    valor_minimo, valor_maximo = st.slider(
        "Intervalo de Nº Pedidos de Reserva",
        min_value=min_valor,
        max_value=max_valor,
        value=(min_valor, max_valor),
        help="Filtra produtos por popularidade. Produtos com mais reservas tendem a ser críticos para a gestão de stock."
    )

    report_pivot = report_pivot[
        (report_pivot[('Total', 'Nº Pedidos de Reserva')] >= valor_minimo) &
        (report_pivot[('Total', 'Nº Pedidos de Reserva')] <= valor_maximo)
    ]

    report_pivot = report_pivot.sort_values(by=('Total', 'Nº Pedidos de Reserva'), ascending=False)

    # Função para aplicar cores aos grupos de colunas
    def color_by_group(df):
        styles = pd.DataFrame('', index=df.index, columns=df.columns)
        for col in df.columns:
            if col[0] == 'Nº Pedidos de Reserva':
                styles[col] = 'background-color: rgba(108, 28, 204, 0.9 ); color: #FFFFFF; font-weight: bold;text-align: center;'
            elif col[0] == 'Unidades Reservadas':
                styles[col] = 'background-color: rgba(86, 58, 217, 0.9 ); color: #FFFFFF; font-weight: bold;text-align: center;'
            elif col[0] == 'Total':
                styles[col] ='background-color: rgba(24, 0, 57, 0.9 ); color: #FFFFFF; font-weight: bold; text-align: center; '             
            
        return styles

    styled_df = report_pivot.style.apply(color_by_group, axis=None).set_properties(**{'text-align': 'center', 'vertical-align': 'middle'})
    
    st.info(
    """
    ℹ️ **Como interpretar os dados:**
    
    - **Nº Pedidos de Reserva:** mostra a frequência com que um produto foi reservado.
        - Ex. 2 Unidades reservadas no mesmo atendimento correspondem apenas a 1 Reserva  
    - **Unidades Reservadas:** indica o volume total de caixas pedidas.
        - Ex. 2 Unidades reservadas no mesmo atendimento correspondem a 2 unidades reservadas
    
    Um produto com **muitos pedidos mas poucas unidades** pode ter procura dispersa;  
    já um produto com **poucos pedidos mas muitas unidades** pode estar associado a  
    um número restrito de clientes de alto volume.
    """
)

    st.dataframe(styled_df, use_container_width=True)



else:
    st.header("Por favor, carregue o ficheiro de exportação das reservas para  visualizar os dados.")
    
    
