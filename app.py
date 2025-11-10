import streamlit as st 
import pandas as pd 
from datetime import datetime, timedelta
import plotly.express as px 

# ===============================
# 🎨 Estilo customizado
# ===============================
st.set_page_config(page_title="📊 Detector de Lateralizações", layout="wide")
st.markdown("""
<style>
.main {
    background-color: #1E1E1E;
    color: #FAFAFA;
}
.css-1d391kg, .css-1lcbmhc {
    background-color: #262730 !important;
    border-radius: 10px;
    padding: 10px;
}
.dataframe {
    background-color: #2E2E2E;
    color: #FAFAFA;
    border-radius: 10px;
    padding: 8px;
}
.stNumberInput, .stTimeInput, .stSelectbox, .stFileUploader {
    border-radius: 10px !important;
}
h1, h2, h3, h4 {
    color: #4CAF50 !important;
    text-align: center;
    font-weight: bold;
}
table td, table th {
    text-align: center !important;
}
</style>
""", unsafe_allow_html=True)

# ===============================
# Tabelas de pontos por ativo
# ===============================
valores_por_ativo = {
    "Mini Índice (WIN)": {3:200,4:600,5:1600,6:3000,7:6200,8:12600,9:25400,10:51000},
    "Mini Dólar (WDO)": {3:5,4:15,5:35,6:75,7:155,8:315,9:635,10:1275}
}

# ===============================
# Funções auxiliares
# ===============================
def contar_alternancia(candles, i, window=6):
    barras = candles['Barras'].tolist()
    indices = candles.index.tolist()
    datas = candles['DataApenas'].tolist()
    
    if i < 1 or datas[i-1] != datas[i] or barras[i] == barras[i-1]:
        return 0, [], []
    
    contagem = 2
    seq = [barras[i-1], barras[i]]
    usados = [indices[i-1], indices[i]]
    ultima = barras[i]
    
    for j in range(i+1, len(barras)):
        if datas[j] != datas[i] or barras[j] == ultima:
            break
        contagem += 1
        seq.append(barras[j])
        usados.append(indices[j])
        ultima = barras[j]
        if contagem == window:
            break
    
    return contagem, seq, usados

def pontos_por_alternancias(n, tabela_pontos):
    return tabela_pontos.get(n, tabela_pontos.get(6, 3000))

def simular(candles, max_levels=350, window=6, contratos=1, tabela_pontos=None, ativo_escolhido=None):
    sequencias, usados_totais = [], set()
    nivel, i = 1, 0
    seq, esperar_reset = {}, False
    candles_mesmo_lado, ultimo_lado = 0, None
    stop = 5 if ativo_escolhido and "Dólar" in ativo_escolhido else 200
    
    while i < len(candles):
        if i in usados_totais:
            if i - 1 in usados_totais:
                pass
            else:
                i += 1
                continue
        
        if esperar_reset:
            lado_atual = candles["Barras"].iloc[i]
            lado_anterior = candles["Barras"].iloc[i-1] if i > 0 else None
            
            if lado_atual == lado_anterior:
                if lado_atual == ultimo_lado:
                    candles_mesmo_lado += 1
                else:
                    candles_mesmo_lado, ultimo_lado = 1, lado_atual
                
                if candles_mesmo_lado >= 2:
                    esperar_reset, candles_mesmo_lado, ultimo_lado = False, 0, None
            else:
                candles_mesmo_lado, ultimo_lado = 1, lado_atual
            
            i += 1
            continue
        
        if nivel > max_levels:
            nivel, seq = 1, {}
            sequencias.append(seq)
        
        alternados, padrao, usados = contar_alternancia(candles, i, window)
        
        if alternados > 1:
            if all(idx in usados_totais for idx in usados):
                i += 1
                continue
            
            if alternados >= window:
                pontos_base = pontos_por_alternancias(alternados, tabela_pontos)
                pontos = pontos_base * contratos
                seq[nivel] = f"+{pontos} | Seq: {''.join(map(str, padrao))} | Linhas: {usados} | Dia: {candles['DataApenas'].iloc[i]}"
                sequencias.append(seq)
                seq = {}
                nivel = 1
                usados_totais.update(usados)
                esperar_reset, candles_mesmo_lado, ultimo_lado = True, 0, None
                i = usados[-2] if len(usados) > 1 else usados[-1]
                continue
            else:
                pontos = -stop * contratos
                seq[nivel] = f"{pontos} | Seq: {''.join(map(str, padrao))} | Linhas: {usados} | Dia: {candles['DataApenas'].iloc[i]}"
                nivel += 1
                usados_totais.update(usados)
                i = usados[-1] + 1
                continue
        
        i += 1
    
    if seq:
        sequencias.append(seq)
    
    df_result = pd.DataFrame(sequencias).T
    df_result.index.name = "Nível"
    return df_result

def calcular_media_stops_entre_ganhos_por_linha(df):
    """Calcula a média de stops entre ganhos, considerando apenas operações reais"""
    medias = []
    for idx, linha in df.iterrows():
        # Filtrar apenas valores que são stops ou gains (diferentes de zero e não NaN)
        valores = [v for v in linha.drop('Total por Linha', errors='ignore') 
                  if pd.notna(v) and v != 0]
        
        contadores = []
        count_stops = 0
        
        for v in valores:
            if v > 0:  # Gain
                contadores.append(count_stops)
                count_stops = 0
            else:  # Stop (v < 0)
                count_stops += 1
        
        # Se terminou com stops, adicionar ao contador
        if count_stops > 0:
            contadores.append(count_stops)
        
        # Calcular média apenas se houve ganhos
        if contadores:
            media_linha = sum(contadores) / len(contadores)
        else:
            media_linha = 0  # Se não houve ganhos, média é zero
        
        medias.append(media_linha)
    
    return medias

def extrair_stops_entre_gains_por_nivel(df, nivel):
    """Extrai sequência de stops entre gains para um nível específico"""
    linha = df.loc[nivel]
    # Filtrar apenas valores que são stops ou gains
    valores = [v for v in linha.drop('Total por Linha', errors='ignore') 
              if pd.notna(v) and v != 0]
    
    stops_entre_gains = []
    count_stops = 0
    
    for v in valores:
        if v > 0:  # Gain
            stops_entre_gains.append(count_stops)
            count_stops = 0
        else:  # Stop (v < 0)
            count_stops += 1
    
    # Se terminou com stops, adicionar ao contador
    if count_stops > 0:
        stops_entre_gains.append(count_stops)
    
    return stops_entre_gains

def calcular_probabilidade_ganho_por_nivel(df_numerico):
    """Calcula a probabilidade de ganho para cada nível considerando apenas operações reais"""
    probabilidades = {}
    
    for nivel in df_numerico.index:
        if nivel == "TOTAL":
            continue
            
        linha = df_numerico.loc[nivel]
        # Filtrar apenas valores que são stops ou gains (diferentes de zero e não NaN)
        valores_validos = [v for v in linha if pd.notna(v) and v != 0]
        
        if not valores_validos:
            probabilidades[nivel] = 0
            continue
            
        ganhos = sum(1 for v in valores_validos if v > 0)
        total = len(valores_validos)
        probabilidade = (ganhos / total) * 100 if total > 0 else 0
        
        probabilidades[nivel] = probabilidade
    
    return probabilidades

def encontrar_colunas_maxima_minima(candles):
    """Encontra as colunas de Máxima e Mínima"""
    colunas_maxima = ['Máxima', 'Maxima', 'MAXIMA', 'Máxima ', 'Maxima ']
    colunas_minima = ['Mínima', 'Minima', 'MINIMA', 'Mínima ', 'Minima ']
    
    coluna_maxima = None
    coluna_minima = None
    
    for col in colunas_maxima:
        if col in candles.columns:
            coluna_maxima = col
            break
    
    for col in colunas_minima:
        if col in candles.columns:
            coluna_minima = col
            break
    
    return coluna_maxima, coluna_minima

def calcular_range_diario(candles, ano=None):
    """Calcula o range diário (MAIOR Máxima do dia - MENOR Mínima do dia)"""
    coluna_maxima, coluna_minima = encontrar_colunas_maxima_minima(candles)
    
    if not coluna_maxima or not coluna_minima:
        return None
    
    # Filtrar por ano se especificado
    candles_filtrado = candles.copy()
    if ano is not None:
        candles_filtrado = candles_filtrado[candles_filtrado['Ano'] == ano]
    
    # Agrupar por dia e encontrar a MAIOR máxima e MENOR mínima de cada dia
    range_por_dia = candles_filtrado.groupby(candles_filtrado['Data'].dt.date).agg({
        coluna_maxima: 'max',
        coluna_minima: 'min'
    })
    
    # Calcular o range: Maior Máxima - Menor Mínima
    range_por_dia['Range_Diario'] = range_por_dia[coluna_maxima] - range_por_dia[coluna_minima]
    
    return range_por_dia

def obter_dias_por_periodo(candles, periodo_dias, ano=None):
    """Obtém os dias específicos usados no cálculo do range para um período"""
    # Calcular range diário
    range_diario_completo = calcular_range_diario(candles, ano)
    if range_diario_completo is None:
        return pd.DataFrame()
    
    # Ordenar por data (do mais recente para o mais antigo)
    range_diario_completo = range_diario_completo.sort_index(ascending=False)
    
    # Pegar os N dias mais recentes (últimos N dias úteis)
    range_periodo = range_diario_completo.head(periodo_dias)
    
    return range_periodo

def calcular_media_range_por_periodo(candles, periodo_dias, ano=None):
    """Calcula a média do range para um período específico (últimos N dias úteis)"""
    # Obter os dias do período
    range_periodo = obter_dias_por_periodo(candles, periodo_dias, ano)
    
    if range_periodo.empty:
        return 0
    
    # Calcular média do range no período
    media_range = range_periodo['Range_Diario'].mean()
    return round(media_range, 2)

# ===============================
# NOVAS FUNÇÕES PARA ESTATÍSTICA DE BARRAS - SEPARADAS POR CATEGORIA
# ===============================
def analisar_sequencias_barras_por_categoria(candles, max_sequencia=5):
    """
    Analisa as probabilidades de sequências de barras separadas por categoria
    Retorna 3 DataFrames: laterais, compradoras e vendedoras
    """
    barras = candles['Barras'].tolist()
    
    # Contadores para padrões
    padroes_antecessores = {}
    contagem_total = 0
    
    for i in range(len(barras) - 1):
        # Verificar sequências anteriores
        for seq_len in range(1, max_sequencia + 1):
            if i >= seq_len:
                # Criar chave do padrão (ex: "11" para duas compradoras seguidas)
                padrao_anterior = ''.join(str(barras[i-j]) for j in range(seq_len, 0, -1))
                proxima_barra = barras[i]
                
                chave = f"{seq_len}_{padrao_anterior}"
                if chave not in padroes_antecessores:
                    padroes_antecessores[chave] = {'total': 0, 'proximas': {0: 0, 1: 0}}
                
                padroes_antecessores[chave]['total'] += 1
                padroes_antecessores[chave]['proximas'][proxima_barra] += 1
                contagem_total += 1
    
    # Calcular probabilidades e separar por categoria
    resultados_laterais = []
    resultados_compradoras = []
    resultados_vendedoras = []
    
    for padrao, dados in padroes_antecessores.items():
        seq_len, sequencia = padrao.split('_')
        total_ocorrencias = dados['total']
        compradoras_seguintes = dados['proximas'][1]
        vendedoras_seguintes = dados['proximas'][0]
        
        prob_compradora = (compradoras_seguintes / total_ocorrencias * 100) if total_ocorrencias > 0 else 0
        prob_vendedora = (vendedoras_seguintes / total_ocorrencias * 100) if total_ocorrencias > 0 else 0
        
        resultado = {
            'Sequência Anterior': sequencia,
            'Tamanho Sequência': int(seq_len),
            'Ocorrências': total_ocorrencias,
            'Próxima Compradora': compradoras_seguintes,
            'Próxima Vendedora': vendedoras_seguintes,
            'Prob. Compradora (%)': round(prob_compradora, 2),
            'Prob. Vendedora (%)': round(prob_vendedora, 2),
            'Viés': 'Comprador' if prob_compradora > 60 else 'Vendedor' if prob_vendedora > 60 else 'Neutro'
        }
        
        # Classificar em categorias
        if len(set(sequencia)) > 1:  # Sequência mista (0 e 1) - LATERAL
            resultados_laterais.append(resultado)
        elif sequencia == '1' * len(sequencia):  # Apenas 1s - COMPRADORA
            resultados_compradoras.append(resultado)
        elif sequencia == '0' * len(sequencia):  # Apenas 0s - VENDEDORA
            resultados_vendedoras.append(resultado)
    
    # Converter para DataFrames e ordenar
    df_laterais = pd.DataFrame(resultados_laterais).sort_values(['Tamanho Sequência', 'Ocorrências'], ascending=[True, False])
    df_compradoras = pd.DataFrame(resultados_compradoras).sort_values(['Tamanho Sequência', 'Ocorrências'], ascending=[True, False])
    df_vendedoras = pd.DataFrame(resultados_vendedoras).sort_values(['Tamanho Sequência', 'Ocorrências'], ascending=[True, False])
    
    return df_laterais, df_compradoras, df_vendedoras

def calcular_frequencia_barras(candles):
    """Calcula a frequência simples de barras compradoras e vendedoras"""
    barras = candles['Barras'].tolist()
    total = len(barras)
    compradoras = sum(barras)
    vendedoras = total - compradoras
    
    return {
        'Total Barras': total,
        'Compradoras': compradoras,
        'Vendedoras': vendedoras,
        '% Compradoras': round((compradoras / total) * 100, 2),
        '% Vendedoras': round((vendedoras / total) * 100, 2)
    }

# ===============================
# NOVA FUNÇÃO PARA FILTRAR POR PERÍODO
# ===============================
def filtrar_por_periodo(candles, periodo):
    """
    Filtra os candles por período (30 dias, 3 meses, 6 meses)
    """
    if candles.empty or 'Data' not in candles.columns:
        return candles
    
    data_atual = candles['Data'].max()
    
    if periodo == '30 dias':
        data_inicio = data_atual - timedelta(days=30)
    elif periodo == '3 meses':
        data_inicio = data_atual - timedelta(days=90)
    elif periodo == '6 meses':
        data_inicio = data_atual - timedelta(days=180)
    else:  # Ano completo
        return candles
    
    candles_filtrado = candles[candles['Data'] >= data_inicio]
    return candles_filtrado

# ===============================
# NOVA FUNÇÃO PARA CALCULAR ESTATÍSTICAS POR PERÍODO
# ===============================
def calcular_estatisticas_por_periodo(candles, periodo, hora_inicio, hora_fim, window, contratos, tabela_pontos, ativo_escolhido):
    """Calcula estatísticas para um período específico"""
    # Filtrar por período
    dados_periodo = filtrar_por_periodo(candles, periodo)
    
    # Aplicar filtros adicionais
    dados_periodo = dados_periodo[
        (dados_periodo["Hora"] >= hora_inicio) & 
        (dados_periodo["Hora"] <= hora_fim)
    ]
    
    # Inverter ordem
    dados_periodo = dados_periodo.iloc[::-1].reset_index(drop=True)
    
    # Executar simulação
    resultado = simular(
        dados_periodo,
        window=window,
        contratos=contratos,
        tabela_pontos=tabela_pontos,
        ativo_escolhido=ativo_escolhido
    )
    
    # Calcular totais
    if not resultado.empty:
        resultado_numerico = resultado.applymap(
            lambda x: int(x.split()[0]) if isinstance(x, str) and x.split()[0].lstrip("+-").isdigit() else 0
        )
        
        resultado["Total por Linha"] = resultado_numerico.sum(axis=1)
        total_linha = resultado_numerico.sum()
        total_linha["Total por Linha"] = resultado["Total por Linha"].sum()
        resultado.loc["TOTAL"] = total_linha
        
        return resultado, resultado_numerico
    else:
        return pd.DataFrame(), pd.DataFrame()

# ===============================
# FUNÇÃO CORRIGIDA PARA EVOLUÇÃO TEMPORAL DE PROBABILIDADES
# ===============================
def calcular_evolucao_probabilidade_sequencia(candles, sequencia_alvo, tipo_probabilidade='Compradora', janela_dias=7):
    """
    Calcula a evolução temporal da probabilidade para uma sequência específica
    VERSÃO CORRIGIDA - cálculo correto da média móvel
    """
    if candles.empty or 'Data' not in candles.columns:
        return pd.DataFrame()
    
    # Garantir que os dados estão ordenados por data
    candles = candles.sort_values('Data').reset_index(drop=True)
    
    barras = candles['Barras'].tolist()
    datas = candles['Data'].tolist()
    
    # Preparar dados para análise temporal
    dados_temporais = []
    tamanho_sequencia = len(sequencia_alvo)
    
    for i in range(tamanho_sequencia, len(barras) - 1):
        # Verificar se a sequência anterior corresponde ao alvo
        sequencia_anterior = ''.join(str(barras[i-j]) for j in range(tamanho_sequencia, 0, -1))
        
        if sequencia_anterior == sequencia_alvo:
            data_atual = datas[i]
            proxima_barra = barras[i]
            
            dados_temporais.append({
                'Data': data_atual.date(),  # Usar apenas a data (sem hora)
                'Data_Completa': data_atual,
                'Sequência': sequencia_alvo,
                'Próxima_Barra': proxima_barra,
                'Sucesso': 1 if (tipo_probabilidade == 'Compradora' and proxima_barra == 1) or 
                                (tipo_probabilidade == 'Vendedora' and proxima_barra == 0) else 0
            })
    
    if not dados_temporais:
        return pd.DataFrame()
    
    # Criar DataFrame temporal
    df_temporal = pd.DataFrame(dados_temporais)
    
    # CORREÇÃO: Agrupar por data corretamente
    df_diario = df_temporal.groupby('Data').agg({
        'Sucesso': ['count', 'sum'],
        'Data_Completa': 'first'
    }).reset_index()
    
    # Ajustar nomes das colunas
    df_diario.columns = ['Data', 'Total_Ocorrencias', 'Total_Sucessos', 'Data_Ref']
    df_diario = df_diario.sort_values('Data_Ref').reset_index(drop=True)
    
    # Calcular probabilidade diária
    df_diario['Probabilidade_Diaria'] = (df_diario['Total_Sucessos'] / df_diario['Total_Ocorrencias']) * 100
    
    # CORREÇÃO: Calcular média móvel sobre probabilidades diárias
    df_diario['Probabilidade_Media_Movel'] = df_diario['Probabilidade_Diaria'].rolling(
        window=min(janela_dias, len(df_diario)),
        min_periods=1
    ).mean()
    
    # Calcular totais acumulados - CORREÇÃO APLICADA AQUI
    df_diario['Ocorrencias_Acumuladas'] = df_diario['Total_Ocorrencias'].cumsum()
    df_diario['Sucessos_Acumulados'] = df_diario['Total_Sucessos'].cumsum()
    df_diario['Probabilidade_Acumulada'] = (df_diario['Sucessos_Acumulados'] / df_diario['Ocorrencias_Acumuladas']) * 100
    
    return df_diario

# ===============================
# STREAMLIT APP
# ===============================
st.markdown("<h1>📊 Detector de Lateralizações (Ano a Ano, Ordem Invertida)</h1>", unsafe_allow_html=True)

uploaded_file = st.file_uploader("📂 Carregue seu arquivo Excel com os candles", type=["xlsx"])

if uploaded_file:
    candles = pd.read_excel(uploaded_file)
    
    # Corrigir nomes de colunas - remover espaços extras
    candles.columns = candles.columns.str.strip()
    
    with st.expander("📋 Estrutura do Arquivo Lido"):
        st.write("Colunas detectadas:", list(candles.columns))
        st.write("Dimensão (linhas, colunas):", candles.shape)
    
    if "Data" not in candles.columns:
        st.error("⚠ Sua planilha precisa ter uma coluna chamada 'Data'.")
    else:
        candles["Data"] = pd.to_datetime(candles["Data"], dayfirst=True, errors="coerce")
        candles["Ano"] = candles["Data"].dt.year
        candles["DataApenas"] = candles["Data"].dt.date.astype(str)
        candles["Hora"] = candles["Data"].dt.time
        candles["Data_BR"] = candles["Data"].dt.strftime("%d/%m/%Y %H:%M")
        
        ativo_escolhido = st.selectbox("💹 Selecione o Ativo:", list(valores_por_ativo.keys()))
        tabela_pontos_ativa = valores_por_ativo[ativo_escolhido]
        
        anos_disponiveis = sorted(candles["Ano"].unique(), reverse=True)
        ano_escolhido = st.selectbox("📅 Escolha o Ano para Analisar:", anos_disponiveis)
        
        col1, col2, col3 = st.columns(3)
        with col1:
            window = st.number_input("🔢 Window (nº de alternâncias p/ Gain)", min_value=2, max_value=10, value=6)
        with col2:
            contratos = st.number_input("📑 Nº de Contratos", min_value=1, value=1)
        with col3:
            hora_inicio = st.time_input("⏰ Hora Inicial", value=pd.to_datetime("09:00").time())
            hora_fim = st.time_input("⏰ Hora Final", value=pd.to_datetime("12:02").time())
        
        # Garantir que todas as colunas necessárias estejam presentes nos dados filtrados
        colunas_necessarias = ["Data", "Barras", "DataApenas", "Hora", "Data_BR", "Ano"]
        
        # Adicionar colunas de Máxima e Mínima se existirem
        coluna_maxima, coluna_minima = encontrar_colunas_maxima_minima(candles)
        if coluna_maxima and coluna_minima:
            colunas_necessarias.extend([coluna_maxima, coluna_minima])
            st.success(f"✅ Colunas detectadas: '{coluna_maxima}' e '{coluna_minima}'")
        
        dados_filtrados = candles[candles["Ano"] == ano_escolhido]
        dados_filtrados = dados_filtrados[
            (dados_filtrados["Hora"] >= hora_inicio) & 
            (dados_filtrados["Hora"] <= hora_fim)
        ]
        dados_filtrados = dados_filtrados[colunas_necessarias]
        dados_filtrados = dados_filtrados.iloc[::-1].reset_index(drop=True)
        
        tab1, tab2, tab3, tab4 = st.tabs(["📈 Sequências", "📊 Estatísticas", "🎯 Probabilidades", "📊 Estatística de Barras"])
        
        with tab1:
            st.subheader(f"🔎 Dados Filtrados - Ano {ano_escolhido} (≥{hora_inicio}, ≤{hora_fim}, invertidos)")
            # Mostrar todas as colunas disponíveis
            colunas_para_mostrar = ["Data_BR", "Barras"]
            if coluna_maxima and coluna_minima:
                colunas_para_mostrar.extend([coluna_maxima, coluna_minima])
            st.dataframe(dados_filtrados[colunas_para_mostrar])
            
            resultado = simular(
                dados_filtrados,
                window=window,
                contratos=contratos,
                tabela_pontos=tabela_pontos_ativa,
                ativo_escolhido=ativo_escolhido
            )
            
            st.subheader("📈 Sequências de Stops (-200 ou -5) e Gains (escalonados) + Linhas Usadas")
            
            resultado_numerico = resultado.applymap(
                lambda x: int(x.split()[0]) if isinstance(x, str) and x.split()[0].lstrip("+-").isdigit() else 0
            )
            
            resultado["Total por Linha"] = resultado_numerico.sum(axis=1)
            total_linha = resultado_numerico.sum()
            total_linha["Total por Linha"] = resultado["Total por Linha"].sum()
            resultado.loc["TOTAL"] = total_linha
            
            st.dataframe(resultado)
        
        with tab2:
            st.subheader("📊 Estatísticas")
            
            # NOVA SEÇÃO: PERIODICIDADE NAS ESTATÍSTICAS
            st.markdown("---")
            st.subheader("📅 Estatísticas por Período")
            
            # Seleção de período
            periodo_estatistica = st.selectbox(
                "Selecione o período para análise:",
                ["Ano completo", "30 dias", "3 meses", "6 meses"],
                key="periodo_estatistica"
            )
            
            # Calcular estatísticas para o período selecionado
            if periodo_estatistica != "Ano completo":
                # Usar dados completos do ano selecionado
                dados_completos_ano = candles[candles["Ano"] == ano_escolhido].copy()
                resultado_periodo, resultado_numerico_periodo = calcular_estatisticas_por_periodo(
                    dados_completos_ano, periodo_estatistica, hora_inicio, hora_fim, 
                    window, contratos, tabela_pontos_ativa, ativo_escolhido
                )
                
                if not resultado_periodo.empty:
                    st.success(f"*Período analisado:* {periodo_estatistica} | *Ano:* {ano_escolhido}")
                    
                    # Mostrar somatório por linha para o período
                    st.subheader(f"📊 Somatório por Linha - {periodo_estatistica}")
                    
                    # Extrair apenas a coluna de totais
                    totais_periodo = resultado_periodo[["Total por Linha"]].copy()
                    
                    # Formatar para melhor visualização
                    st.dataframe(totais_periodo.style.format({
                        'Total por Linha': '{:,.0f}'
                    }))
                    
                    # Calcular estatísticas financeiras
                    saldo_total_periodo = resultado_numerico_periodo.sum().sum()
                    valor_ponto = 10.0 if "Dólar" in ativo_escolhido else 0.20
                    financeiro_total_periodo = saldo_total_periodo * valor_ponto
                    
                    col1, col2 = st.columns(2)
                    col1.metric(f"🎯 Saldo Total {periodo_estatistica} (pontos)", saldo_total_periodo)
                    col2.metric(f"💰 Saldo Financeiro {periodo_estatistica} (R$)", f"{financeiro_total_periodo:,.2f}")
                    
                    # Gráfico de barras dos totais por linha
                    st.subheader(f"📈 Distribuição por Linha - {periodo_estatistica}")
                    
                    # Preparar dados para o gráfico (excluir linha TOTAL)
                    dados_grafico = totais_periodo[totais_periodo.index != "TOTAL"].copy()
                    if not dados_grafico.empty:
                        fig_totais = px.bar(
                            dados_grafico.reset_index(),
                            x='Nível',
                            y='Total por Linha',
                            title=f'Total por Linha - {periodo_estatistica}',
                            color='Total por Linha',
                            color_continuous_scale='RdYlGn'
                        )
                        st.plotly_chart(fig_totais, use_container_width=True)
                    
                    # Estatísticas adicionais
                    st.subheader(f"📋 Estatísticas Detalhadas - {periodo_estatistica}")
                    
                    # Calcular médias de stops entre ganhos
                    if not resultado_numerico_periodo.empty:
                        medias_por_linha_periodo = calcular_media_stops_entre_ganhos_por_linha(resultado_numerico_periodo)
                        df_medias_periodo = pd.DataFrame({
                            'Linha': resultado_numerico_periodo.index,
                            'Média Stops entre Ganhos': medias_por_linha_periodo
                        }).set_index('Linha')
                        
                        st.write("*Média de Stops entre Ganhos por Linha:*")
                        st.dataframe(df_medias_periodo)
                        
                        # Calcular média geral
                        linhas_com_ganhos_periodo = df_medias_periodo[df_medias_periodo['Média Stops entre Ganhos'] > 0]
                        if not linhas_com_ganhos_periodo.empty:
                            media_geral_periodo = linhas_com_ganhos_periodo['Média Stops entre Ganhos'].mean()
                            st.write(f"*Média Geral de Stops entre Ganhos:* {media_geral_periodo:.2f}")
                
                else:
                    st.warning(f"Não foram encontrados dados para o período {periodo_estatistica} no ano {ano_escolhido}")
            
            else:
                # Usar dados do ano completo (comportamento original)
                saldo_total = resultado_numerico.sum().sum()
                valor_ponto = 10.0 if "Dólar" in ativo_escolhido else 0.20
                financeiro_total = saldo_total * valor_ponto
                
                col1, col2 = st.columns(2)
                col1.metric("🎯 Saldo Total (pontos)", saldo_total)
                col2.metric("💰 Saldo Financeiro (R$)", f"{financeiro_total:,.2f}")
                
                tabela_totais = resultado[["Total por Linha"]].to_html(escape=False, index=True)
                st.subheader("📊 Somatório por Linha")
                st.markdown(f"<div style='text-align:center'>{tabela_totais}</div>", unsafe_allow_html=True)
                
                ganhos_por_nivel = (resultado_numerico > 0).sum(axis=1)
                st.bar_chart(ganhos_por_nivel)
                
                # CORREÇÃO APLICADA AQUI - média de stops entre ganhos
                medias_por_linha = calcular_media_stops_entre_ganhos_por_linha(resultado_numerico)
                df_medias = pd.DataFrame({
                    'Linha': resultado_numerico.index,
                    'Média Stops entre Ganhos': medias_por_linha
                }).set_index('Linha')
                
                st.subheader("📉 Média de Stops entre Ganhos por Linha")
                st.dataframe(df_medias)
                
                # Calcular média geral apenas para linhas que tiveram ganhos
                linhas_com_ganhos = df_medias[df_medias['Média Stops entre Ganhos'] > 0]
                if not linhas_com_ganhos.empty:
                    media_geral = linhas_com_ganhos['Média Stops entre Ganhos'].mean()
                else:
                    media_geral = 0
                    
                st.write(f"Média Geral de Stops entre Ganhos: {media_geral:.2f}")
                st.bar_chart(df_medias['Média Stops entre Ganhos'])
            
            # --- GRÁFICO: Evolução dos Stops ---
            st.markdown("---")
            st.subheader("📈 Evolução dos Stops entre Ganhos")
            
            modo_visualizacao = st.radio(
                "Escolha o modo de visualização:",
                ["Ano + Nível específico", "Comparar anos"],
                key="modo_visualizacao_estat"
            )
            
            limite_stops = st.number_input(
                "Defina o limite de Stops entre Ganhos (linha amarela)",
                min_value=1, value=20,
                key="limite_stops_estat"
            )
            
            if modo_visualizacao == "Comparar anos":
                anos_escolhidos = st.multiselect(
                    "Selecione os anos para comparar:",
                    anos_disponiveis, default=anos_disponiveis,
                    key="anos_comparacao_estat"
                )
                
                niveis_disponiveis_geral = [lvl for lvl in resultado_numerico.index if lvl != "TOTAL"]
                if not niveis_disponiveis_geral:
                    st.info("Não há níveis disponíveis para comparação.")
                else:
                    nivel_ref = st.selectbox(
                        "Selecione o nível para referência na comparação entre anos:",
                        niveis_disponiveis_geral,
                        key="nivel_ref_estat"
                    )
                    
                    dfs = []
                    for ano in anos_escolhidos:
                        dados_ano = candles[candles["Ano"] == ano]
                        dados_ano = dados_ano[
                            (dados_ano["Hora"] >= hora_inicio) & 
                            (dados_ano["Hora"] <= hora_fim)
                        ]
                        dados_ano = dados_ano[colunas_necessarias]
                        dados_ano = dados_ano.iloc[::-1].reset_index(drop=True)
                        
                        resultado_ano = simular(
                            dados_ano,
                            window=window,
                            contratos=contratos,
                            tabela_pontos=tabela_pontos_ativa,
                            ativo_escolhido=ativo_escolhido
                        )
                        
                        resultado_numerico_ano = resultado_ano.applymap(
                            lambda x: int(x.split()[0]) if isinstance(x, str) and x.split()[0].lstrip("+-").isdigit() else 0
                        ) if not resultado_ano.empty else pd.DataFrame()
                        
                        if resultado_numerico_ano.empty or nivel_ref not in resultado_numerico_ano.index:
                            continue
                        
                        sequencia_stops = extrair_stops_entre_gains_por_nivel(resultado_numerico_ano, nivel_ref)
                        if len(sequencia_stops) > 0:
                            df_temp = pd.DataFrame({
                                "Ordem": list(range(1, len(sequencia_stops)+1)),
                                "Stops entre Ganhos": sequencia_stops,
                                "Ano": ano
                            })
                            dfs.append(df_temp)
                    
                    if len(dfs) == 0:
                        st.info("Não há dados suficientes para exibir a comparação.")
                    else:
                        df_hist = pd.concat(dfs, ignore_index=True)
                        
                        # --- CALCULO DA MÉDIA EVOLUTIVA ---
                        dfs_me = []
                        for ano in anos_escolhidos:
                            df_ano = df_hist[df_hist['Ano'] == ano].copy()
                            df_ano['Média Evolutiva'] = df_ano['Stops entre Ganhos'].expanding().mean()
                            dfs_me.append(df_ano)
                        
                        df_hist_me = pd.concat(dfs_me, ignore_index=True)
                        
                        # --- PLOTAGEM ---
                        fig = px.line(
                            df_hist,
                            x="Ordem",
                            y="Stops entre Ganhos",
                            color="Ano",
                            markers=True,
                            title=f'Histórico de Stops entre Ganhos - Nível {nivel_ref}'
                        )
                        
                        fig.add_hline(
                            y=limite_stops,
                            line_dash="dash",
                            line_color="yellow",
                            annotation_text=f"Limite = {limite_stops}",
                            annotation_position="top left"
                        )
                        
                        # --- LINHA MÉDIA EVOLUTIVA ---
                        for ano in anos_escolhidos:
                            df_ano_me = df_hist_me[df_hist_me['Ano'] == ano]
                            fig.add_scatter(
                                x=df_ano_me['Ordem'],
                                y=df_ano_me['Média Evolutiva'],
                                mode='lines',
                                line=dict(color='magenta', dash='dash'),
                                name=f'Média Evolutiva {ano}'
                            )
                        
                        st.plotly_chart(fig, use_container_width=True)
            
            else:
                niveis_disponiveis = [lvl for lvl in resultado_numerico.index if lvl != "TOTAL"]
                nivel_selecionado = st.selectbox(
                    "Selecione o nível para ver a evolução:", 
                    niveis_disponiveis,
                    key="nivel_selecionado_estat"
                )
                
                sequencia_stops = extrair_stops_entre_gains_por_nivel(resultado_numerico, nivel_selecionado)
                
                if len(sequencia_stops) == 0:
                    st.info("Não há dados suficientes para exibir.")
                else:
                    df_graf = pd.DataFrame({
                        'Ordem': list(range(1, len(sequencia_stops)+1)),
                        'Stops entre Ganhos': sequencia_stops
                    })
                    
                    df_graf['Média Evolutiva'] = df_graf['Stops entre Ganhos'].expanding().mean()
                    
                    fig = px.line(
                        df_graf,
                        x='Ordem',
                        y='Stops entre Ganhos',
                        markers=True,
                        title=f'Stops entre Ganhos no Nível {nivel_selecionado}'
                    )
                    
                    fig.add_hline(
                        y=limite_stops,
                        line_dash="dash",
                        line_color="yellow",
                        annotation_text=f"Limite = {limite_stops}",
                        annotation_position="top left"
                    )
                    
                    fig.add_scatter(
                        x=df_graf['Ordem'],
                        y=df_graf['Média Evolutiva'],
                        mode='lines',
                        line=dict(color='magenta', dash='dash'),
                        name='Média Evolutiva'
                    )
                    
                    st.plotly_chart(fig, use_container_width=True)
        
        with tab3:
            st.subheader("🎯 Probabilidade de Ganho por Nível")
            
            # Calcular probabilidades
            probabilidades = calcular_probabilidade_ganho_por_nivel(resultado_numerico)
            
            # Criar DataFrame para exibição
            df_probabilidades = pd.DataFrame({
                'Nível': list(probabilidades.keys()),
                'Probabilidade de Ganho (%)': list(probabilidades.values())
            }).set_index('Nível')
            
            # Adicionar informações adicionais
            df_probabilidades['Total Ocorrências'] = [
                len([v for v in resultado_numerico.loc[nivel] if pd.notna(v) and v != 0]) 
                for nivel in probabilidades.keys()
            ]
            df_probabilidades['Ganhos'] = [
                sum(1 for v in resultado_numerico.loc[nivel] if v > 0) 
                for nivel in probabilidades.keys()
            ]
            df_probabilidades['Stops'] = [
                sum(1 for v in resultado_numerico.loc[nivel] if v < 0) 
                for nivel in probabilidades.keys()
            ]
            
            # Ordenar por nível
            df_probabilidades = df_probabilidades.sort_index()
            
            st.dataframe(df_probabilidades.style.format({
                'Probabilidade de Ganho (%)': '{:.2f}%',
                'Total Ocorrências': '{:.0f}',
                'Ganhos': '{:.0f}',
                'Stops': '{:.0f}'
            }))
            
            # Gráfico de probabilidades
            fig_prob = px.bar(
                df_probabilidades.reset_index(),
                x='Nível',
                y='Probabilidade de Ganho (%)',
                title='Probabilidade de Ganho por Nível',
                color='Probabilidade de Ganho (%)',
                color_continuous_scale='RdYlGn'
            )
            fig_prob.update_layout(
                xaxis_title="Nível",
                yaxis_title="Probabilidade de Ganho (%)",
                yaxis=dict(range=[0, 100])
            )
            st.plotly_chart(fig_prob, use_container_width=True)
            
            # Estatísticas resumidas
            st.subheader("📈 Estatísticas Resumidas das Probabilidades")
            prob_media = df_probabilidades['Probabilidade de Ganho (%)'].mean()
            prob_max = df_probabilidades['Probabilidade de Ganho (%)'].max()
            prob_min = df_probabilidades['Probabilidade de Ganho (%)'].min()
            nivel_maior_prob = df_probabilidades['Probabilidade de Ganho (%)'].idxmax()
            nivel_menor_prob = df_probabilidades['Probabilidade de Ganho (%)'].idxmin()
            
            col1, col2, col3 = st.columns(3)
            col1.metric("📊 Probabilidade Média", f"{prob_media:.2f}%")
            col2.metric("⬆ Maior Probabilidade", f"{prob_max:.2f}%", f"Nível {nivel_maior_prob}")
            col3.metric("⬇ Menor Probabilidade", f"{prob_min:.2f}%", f"Nível {nivel_menor_prob}")
            
            # --- NOVA SEÇÃO: DIAS UTILIZADOS NO CÁLCULO DA MÉDIA DE RANGE ---
            st.markdown("---")
            st.subheader("📅 Dias Utilizados no Cálculo da Média de Range")
            
            # Verificar se as colunas Máxima e Mínima existem
            coluna_maxima, coluna_minima = encontrar_colunas_maxima_minima(candles)
            
            if coluna_maxima and coluna_minima:
                # Calcular médias para diferentes períodos
                media_30_dias = calcular_media_range_por_periodo(candles, 30, ano_escolhido)
                media_3_meses = calcular_media_range_por_periodo(candles, 90, ano_escolhido)
                media_6_meses = calcular_media_range_por_periodo(candles, 180, ano_escolhido)
                
                # Obter os dias específicos usados em cada período
                dias_30 = obter_dias_por_periodo(candles, 30, ano_escolhido)
                dias_90 = obter_dias_por_periodo(candles, 90, ano_escolhido)
                dias_180 = obter_dias_por_periodo(candles, 180, ano_escolhido)
                
                # Criar tabela de resumo
                st.subheader("📊 Resumo dos Períodos")
                df_resumo_range = pd.DataFrame({
                    'Período': ['30 Dias', '3 Meses', '6 Meses'],
                    'Dias Solicitados': [30, 90, 180],
                    'Dias Encontrados': [len(dias_30), len(dias_90), len(dias_180)],
                    'Média do Range': [media_30_dias, media_3_meses, media_6_meses],
                    'Data Inicial': [
                        dias_30.index.min().strftime('%d/%m/%Y') if not dias_30.empty else 'N/A',
                        dias_90.index.min().strftime('%d/%m/%Y') if not dias_90.empty else 'N/A', 
                        dias_180.index.min().strftime('%d/%m/%Y') if not dias_180.empty else 'N/A'
                    ],
                    'Data Final': [
                        dias_30.index.max().strftime('%d/%m/%Y') if not dias_30.empty else 'N/A',
                        dias_90.index.max().strftime('%d/%m/%Y') if not dias_90.empty else 'N/A',
                        dias_180.index.max().strftime('%d/%m/%Y') if not dias_180.empty else 'N/A'
                    ]
                })
                
                st.dataframe(df_resumo_range.style.format({
                    'Média do Range': '{:.2f}'
                }))
                
                # Mostrar dias específicos para cada período
                st.subheader("📋 Dias Específicos por Período")
                
                # 30 DIAS
                with st.expander(f"📅 30 Dias ({len(dias_30)} dias encontrados) - Média: {media_30_dias:.2f}"):
                    if not dias_30.empty:
                        dias_30_display = dias_30.reset_index()
                        dias_30_display.columns = ['Data', 'Maior Máxima', 'Menor Mínima', 'Range Diário']
                        dias_30_display = dias_30_display.sort_values('Data', ascending=False)
                        st.dataframe(dias_30_display.style.format({
                            'Maior Máxima': '{:.0f}',
                            'Menor Mínima': '{:.0f}',
                            'Range Diário': '{:.0f}'
                        }))
                    else:
                        st.info("Nenhum dia encontrado para o período de 30 dias")
                
                # 3 MESES  
                with st.expander(f"📅 3 Meses ({len(dias_90)} dias encontrados) - Média: {media_3_meses:.2f}"):
                    if not dias_90.empty:
                        dias_90_display = dias_90.reset_index()
                        dias_90_display.columns = ['Data', 'Maior Máxima', 'Menor Mínima', 'Range Diário']
                        dias_90_display = dias_90_display.sort_values('Data', ascending=False)
                        st.dataframe(dias_90_display.style.format({
                            'Maior Máxima': '{:.0f}',
                            'Menor Mínima': '{:.0f}',
                            'Range Diário': '{:.0f}'
                        }))
                    else:
                        st.info("Nenhum dia encontrado para o período de 3 meses")
                
                # 6 MESES
                with st.expander(f"📅 6 Meses ({len(dias_180)} dias encontrados) - Média: {media_6_meses:.2f}"):
                    if not dias_180.empty:
                        dias_180_display = dias_180.reset_index()
                        dias_180_display.columns = ['Data', 'Maior Máxima', 'Menor Mínima', 'Range Diário']
                        dias_180_display = dias_180_display.sort_values('Data', ascending=False)
                        st.dataframe(dias_180_display.style.format({
                            'Maior Máxima': '{:.0f}',
                            'Menor Mínima': '{:.0f}',
                            'Range Diário': '{:.0f}'
                        }))
                    else:
                        st.info("Nenhum dia encontrado para o período de 6 meses")
                
                # Gráfico de linha do range ao longo do ano
                st.markdown("---")
                st.subheader(f"📅 Range Diário - Ano {ano_escolhido}")
                
                range_diario = calcular_range_diario(candles, ano_escolhido)
                if range_diario is not None and not range_diario.empty:
                    # Criar DataFrame com todos os ranges do ano
                    df_range_completo = range_diario.reset_index()
                    df_range_completo.columns = ['Data', 'Maior Máxima', 'Menor Mínima', 'Range Diário']
                    
                    # Ordenar por data
                    df_range_completo = df_range_completo.sort_values('Data', ascending=False)
                    
                    st.write(f"Total de dias no ano {ano_escolhido}: {len(df_range_completo)}")
                    
                    # Mostrar tabela com todos os ranges
                    st.dataframe(df_range_completo.style.format({
                        'Maior Máxima': '{:.0f}',
                        'Menor Mínima': '{:.0f}',
                        'Range Diário': '{:.0f}'
                    }))
                    
                    # Estatísticas do range do ano
                    st.subheader("📊 Estatísticas do Range do Ano")
                    range_medio_ano = df_range_completo['Range Diário'].mean()
                    range_max_ano = df_range_completo['Range Diário'].max()
                    range_min_ano = df_range_completo['Range Diário'].min()
                    dia_maior_range = df_range_completo.loc[df_range_completo['Range Diário'].idxmax(), 'Data']
                    dia_menor_range = df_range_completo.loc[df_range_completo['Range Diário'].idxmin(), 'Data']
                    
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("📊 Range Médio", f"{range_medio_ano:.0f}")
                    col2.metric("⬆ Maior Range", f"{range_max_ano:.0f}", f"Dia {dia_maior_range}")
                    col3.metric("⬇ Menor Range", f"{range_min_ano:.0f}", f"Dia {dia_menor_range}")
                    col4.metric("📅 Dias Analisados", f"{len(df_range_completo)}")
                    
                    # Gráfico de linha do range ao longo do ano
                    fig_range_ano = px.line(
                        df_range_completo.sort_values('Data'),
                        x='Data',
                        y='Range Diário',
                        title=f'Evolução do Range Diário - Ano {ano_escolhido}',
                        markers=True
                    )
                    fig_range_ano.update_layout(
                        xaxis_title="Data",
                        yaxis_title="Range Diário"
                    )
                    st.plotly_chart(fig_range_ano, use_container_width=True)
                    
                    # Mostrar exemplo detalhado para um dia específico
                    with st.expander("🔍 Ver exemplo detalhado de cálculo"):
                        if not df_range_completo.empty:
                            dia_exemplo = df_range_completo['Data'].iloc[0]
                            dados_dia = candles[
                                (candles['Data'].dt.date == dia_exemplo) & 
                                (candles['Ano'] == ano_escolhido)
                            ]
                            
                            maxima_dia = dados_dia[coluna_maxima].max()
                            minima_dia = dados_dia[coluna_minima].min()
                            range_calculado = maxima_dia - minima_dia
                            
                            st.write(f"Dia: {dia_exemplo}")
                            st.write(f"Maior {coluna_maxima} do dia: {maxima_dia}")
                            st.write(f"Menor {coluna_minima} do dia: {minima_dia}")
                            st.write(f"Range calculado: {maxima_dia} - {minima_dia} = {range_calculado}")
                            
                            st.write("Dados do dia (primeiras 10 linhas):")
                            st.dataframe(dados_dia[['Data', coluna_maxima, coluna_minima]].head(10))
                else:
                    st.info(f"Não há dados de range disponíveis para o ano {ano_escolhido}")
                
            else:
                st.warning("⚠ Colunas 'Máxima' e 'Mínima' não foram encontradas no arquivo.")
                st.info("📝 Colunas disponíveis no seu arquivo:")
                st.write(list(candles.columns))
        
        with tab4:
            st.subheader("📊 Estatística de Sequências de Barras")
            
            # NOVO: Seleção de período para análise de barras
            st.markdown("---")
            st.subheader("📅 Configuração do Período de Análise")
            
            col_periodo1, col_periodo2 = st.columns(2)
            
            with col_periodo1:
                periodo_analise = st.selectbox(
                    "Selecione o período para análise:",
                    ["Ano completo", "30 dias", "3 meses", "6 meses"],
                    help="Escolha o período temporal para análise das sequências de barras",
                    key="periodo_analise_barras"
                )
            
            with col_periodo2:
                st.write("ℹ Informações do Período:")
                if periodo_analise == "30 dias":
                    st.write("📊 Análise dos últimos 30 dias")
                elif periodo_analise == "3 meses":
                    st.write("📊 Análise dos últimos 3 meses")
                elif periodo_analise == "6 meses":
                    st.write("📊 Análise dos últimos 6 meses")
                else:
                    st.write("📊 Análise do ano completo")
            
            # Filtrar dados por período selecionado
            dados_barras_periodo = dados_filtrados.copy()
            
            if periodo_analise != "Ano completo":
                dados_barras_periodo = filtrar_por_periodo(dados_barras_periodo, periodo_analise)
            
            # Mostrar informações sobre o período filtrado
            if not dados_barras_periodo.empty:
                data_inicio = dados_barras_periodo['Data'].min().strftime('%d/%m/%Y')
                data_fim = dados_barras_periodo['Data'].max().strftime('%d/%m/%Y')
                total_barras_periodo = len(dados_barras_periodo)
                
                st.success(f"*Período analisado:* {data_inicio} a {data_fim} | *Total de barras:* {total_barras_periodo}")
            else:
                st.warning("Não há dados disponíveis para o período selecionado.")
                dados_barras_periodo = dados_filtrados  # Fallback para dados completos
            
            st.markdown("---")
            
            # Frequência básica das barras (agora usando o período filtrado)
            freq_barras = calcular_frequencia_barras(dados_barras_periodo)
            
            col1, col2, col3, col4 = st.columns(4)
            col1.metric("📊 Total de Barras", freq_barras['Total Barras'])
            col2.metric("🟢 Barras Compradoras", f"{freq_barras['Compradoras']} ({freq_barras['% Compradoras']}%)")
            col3.metric("🔴 Barras Vendedoras", f"{freq_barras['Vendedoras']} ({freq_barras['% Vendedoras']}%)")
            col4.metric("⚖ Viés Geral", 
                        "Comprador" if freq_barras['% Compradoras'] > 55 else "Vendedor" if freq_barras['% Vendedoras'] > 55 else "Neutro")
            
            st.markdown("---")
            
            # Análise de sequências (agora usando o período filtrado)
            st.subheader("🔍 Análise de Probabilidades por Sequência")
            
            max_sequencia = st.slider("Tamanho máximo da sequência analisada:", 2, 6, 3, key="max_sequencia_barras")
            
            # Analisar sequências por categoria
            df_laterais, df_compradoras, df_vendedoras = analisar_sequencias_barras_por_categoria(dados_barras_periodo, max_sequencia)
            
            # Criar abas para cada categoria - AGORA COM 4 ABAS (INCLUINDO EVOLUÇÃO TEMPORAL)
            tab_laterais, tab_compradoras, tab_vendedoras, tab_evolucao = st.tabs([
                "🔄 Sequências Laterais", 
                "🟢 Sequências Compradoras", 
                "🔴 Sequências Vendedoras",
                "📈 Evolução Temporal"
            ])
            
            with tab_laterais:
                st.subheader("🔄 Sequências Laterais (Mistas - 0 e 1)")
                if not df_laterais.empty:
                    colunas_mostrar = ['Sequência Anterior', 'Tamanho Sequência', 'Ocorrências', 
                                      'Prob. Compradora (%)', 'Prob. Vendedora (%)', 'Viés']
                    
                    st.dataframe(df_laterais[colunas_mostrar].style.format({
                        'Prob. Compradora (%)': '{:.2f}%',
                        'Prob. Vendedora (%)': '{:.2f}%'
                    }))
                    
                    # Gráfico para sequências laterais
                    if len(df_laterais) > 0:
                        df_grafico_laterais = df_laterais.copy()
                        df_grafico_laterais['Sequência'] = df_grafico_laterais['Sequência Anterior'] + ' → ?'
                        
                        fig_laterais = px.bar(
                            df_grafico_laterais.head(10),  # Mostrar apenas as top 10
                            x='Sequência',
                            y=['Prob. Compradora (%)', 'Prob. Vendedora (%)'],
                            title=f'Top 10 Sequências Laterais - {periodo_analise}',
                            barmode='group',
                            color_discrete_map={'Prob. Compradora (%)': 'green', 'Prob. Vendedora (%)': 'red'}
                        )
                        fig_laterais.update_layout(
                            xaxis_title="Sequência Anterior",
                            yaxis_title="Probabilidade (%)",
                            yaxis=dict(range=[0, 100])
                        )
                        st.plotly_chart(fig_laterais, use_container_width=True)
                else:
                    st.info("Nenhuma sequência lateral encontrada.")
            
            with tab_compradoras:
                st.subheader("🟢 Sequências Compradoras (Apenas 1s)")
                if not df_compradoras.empty:
                    colunas_mostrar = ['Sequência Anterior', 'Tamanho Sequência', 'Ocorrências', 
                                      'Prob. Compradora (%)', 'Prob. Vendedora (%)', 'Viés']
                    
                    st.dataframe(df_compradoras[colunas_mostrar].style.format({
                        'Prob. Compradora (%)': '{:.2f}%',
                        'Prob. Vendedora (%)': '{:.2f}%'
                    }))
                    
                    # Gráfico para sequências compradoras
                    if len(df_compradoras) > 0:
                        df_grafico_compradoras = df_compradoras.copy()
                        df_grafico_compradoras['Sequência'] = df_grafico_compradoras['Sequência Anterior'] + ' → ?'
                        
                        fig_compradoras = px.bar(
                            df_grafico_compradoras.head(10),  # Mostrar apenas as top 10
                            x='Sequência',
                            y=['Prob. Compradora (%)', 'Prob. Vendedora (%)'],
                            title=f'Top 10 Sequências Compradoras - {periodo_analise}',
                            barmode='group',
                            color_discrete_map={'Prob. Compradora (%)': 'green', 'Prob. Vendedora (%)': 'red'}
                        )
                        fig_compradoras.update_layout(
                            xaxis_title="Sequência Anterior",
                            yaxis_title="Probabilidade (%)",
                            yaxis=dict(range=[0, 100])
                        )
                        st.plotly_chart(fig_compradoras, use_container_width=True)
                else:
                    st.info("Nenhuma sequência compradora encontrada.")
            
            with tab_vendedoras:
                st.subheader("🔴 Sequências Vendedoras (Apenas 0s)")
                if not df_vendedoras.empty:
                    colunas_mostrar = ['Sequência Anterior', 'Tamanho Sequência', 'Ocorrências', 
                                      'Prob. Compradora (%)', 'Prob. Vendedora (%)', 'Viés']
                    
                    st.dataframe(df_vendedoras[colunas_mostrar].style.format({
                        'Prob. Compradora (%)': '{:.2f}%',
                        'Prob. Vendedora (%)': '{:.2f}%'
                    }))
                    
                    # Gráfico para sequências vendedoras
                    if len(df_vendedoras) > 0:
                        df_grafico_vendedoras = df_vendedoras.copy()
                        df_grafico_vendedoras['Sequência'] = df_grafico_vendedoras['Sequência Anterior'] + ' → ?'
                        
                        fig_vendedoras = px.bar(
                            df_grafico_vendedoras.head(10),  # Mostrar apenas as top 10
                            x='Sequência',
                            y=['Prob. Compradora (%)', 'Prob. Vendedora (%)'],
                            title=f'Top 10 Sequências Vendedoras - {periodo_analise}',
                            barmode='group',
                            color_discrete_map={'Prob. Compradora (%)': 'green', 'Prob. Vendedora (%)': 'red'}
                        )
                        fig_vendedoras.update_layout(
                            xaxis_title="Sequência Anterior",
                            yaxis_title="Probabilidade (%)",
                            yaxis=dict(range=[0, 100])
                        )
                        st.plotly_chart(fig_vendedoras, use_container_width=True)
                else:
                    st.info("Nenhuma sequência vendedora encontrada.")
            
            # NOVA ABA: EVOLUÇÃO TEMPORAL
            with tab_evolucao:
                st.subheader("📈 Evolução Temporal das Probabilidades")
                
                # Seleção da sequência para análise
                st.markdown("### 🔍 Seleção da Sequência para Análise")
                
                # Combinar todas as sequências encontradas
                todas_sequencias = []
                if not df_laterais.empty:
                    todas_sequencias.extend(df_laterais['Sequência Anterior'].tolist())
                if not df_compradoras.empty:
                    todas_sequencias.extend(df_compradoras['Sequência Anterior'].tolist())
                if not df_vendedoras.empty:
                    todas_sequencias.extend(df_vendedoras['Sequência Anterior'].tolist())
                
                if todas_sequencias:
                    # Remover duplicatas e ordenar
                    todas_sequencias = sorted(list(set(todas_sequencias)), key=lambda x: (len(x), x))
                    
                    col_seq1, col_seq2, col_seq3 = st.columns(3)
                    
                    with col_seq1:
                        sequencia_selecionada = st.selectbox(
                            "Selecione a sequência:",
                            todas_sequencias,
                            help="Escolha a sequência para analisar a evolução temporal",
                            key="sequencia_evolucao"
                        )
                    
                    with col_seq2:
                        tipo_probabilidade = st.selectbox(
                            "Tipo de probabilidade:",
                            ['Compradora', 'Vendedora'],
                            help="Probabilidade da próxima barra ser compradora ou vendedora",
                            key="tipo_prob_evolucao"
                        )
                    
                    with col_seq3:
                        janela_media = st.number_input(
                            "Janela da média móvel (dias):",
                            min_value=1,
                            max_value=90,
                            value=7,
                            help="Número de dias para a média móvel",
                            key="janela_media_evolucao"
                        )
                    
                    # Calcular evolução temporal
                    if sequencia_selecionada:
                        df_evolucao = calcular_evolucao_probabilidade_sequencia(
                            dados_barras_periodo, 
                            sequencia_selecionada, 
                            tipo_probabilidade,
                            janela_media
                        )
                        
                        if not df_evolucao.empty:
                            # Estatísticas da sequência
                            total_ocorrencias = df_evolucao['Ocorrencias_Acumuladas'].iloc[-1]
                            sucessos = df_evolucao['Sucessos_Acumulados'].iloc[-1]
                            probabilidade_atual = df_evolucao['Probabilidade_Acumulada'].iloc[-1]
                            
                            col_stat1, col_stat2, col_stat3, col_stat4 = st.columns(4)
                            col_stat1.metric("📊 Total Ocorrências", total_ocorrencias)
                            col_stat2.metric("✅ Sucessos", sucessos)
                            col_stat3.metric("❌ Fracassos", total_ocorrencias - sucessos)
                            col_stat4.metric("🎯 Probabilidade Atual", f"{probabilidade_atual:.1f}%")
                            
                            # Explicação do cálculo
                            with st.expander("ℹ️ Como a média móvel é calculada?"):
                                st.markdown(f"""
                                **Método de Cálculo:**
                                
                                1. **Agrupamento por Dia**: Todas as ocorrências da sequência `{sequencia_selecionada}` são agrupadas por data
                                2. **Probabilidade Diária**: Para cada dia, calculamos `(sucessos / total) × 100`
                                3. **Média Móvel**: Para cada dia, calculamos a média das probabilidades dos últimos **{janela_media} dias**
                                
                                **Exemplo com janela de 3 dias:**
                                - Dia 1: 60% (apenas este dia)
                                - Dia 2: (60% + 75%) / 2 = 67.5%
                                - Dia 3: (60% + 75% + 50%) / 3 = 61.7%
                                - Dia 4: (75% + 50% + 71%) / 3 = 65.3%
                                """)
                            
                            # Gráfico de evolução temporal
                            st.markdown("### 📈 Evolução da Probabilidade ao Longo do Tempo")
                            
                            fig_evolucao = px.line(
                                df_evolucao,
                                x='Data',
                                y=['Probabilidade_Acumulada', 'Probabilidade_Media_Movel'],
                                title=f'Evolução da Probabilidade {tipo_probabilidade} - Sequência: {sequencia_selecionada}',
                                labels={
                                    'value': 'Probabilidade (%)',
                                    'variable': 'Tipo de Probabilidade',
                                    'Data': 'Data'
                                }
                            )
                            
                            # Personalizar as linhas
                            fig_evolucao.update_traces(
                                selector=dict(name='Probabilidade_Acumulada'),
                                line=dict(dash='dot', color='blue'),
                                name='Probabilidade Acumulada'
                            )
                            fig_evolucao.update_traces(
                                selector=dict(name='Probabilidade_Media_Movel'),
                                line=dict(dash='solid', color='red'),
                                name=f'Média Móvel ({janela_media} dias)'
                            )
                            
                            # Adicionar linha de referência em 50%
                            fig_evolucao.add_hline(
                                y=50, 
                                line_dash="dash", 
                                line_color="gray",
                                annotation_text="50% (Aleatório)",
                                annotation_position="bottom right"
                            )
                            
                            fig_evolucao.update_layout(
                                xaxis_title="Data",
                                yaxis_title="Probabilidade (%)",
                                yaxis=dict(range=[0, 100]),
                                hovermode='x unified'
                            )
                            
                            st.plotly_chart(fig_evolucao, use_container_width=True)
                            
                            # Tabela com dados detalhados - CORREÇÃO APLICADA AQUI
                            with st.expander("📋 Ver Dados Detalhados da Evolução"):
                                st.write(f"**Sequência:** {sequencia_selecionada} | **Tipo:** {tipo_probabilidade}")
                                df_display = df_evolucao.copy()
                                
                                # CORREÇÃO: Converter a coluna 'Data' para string antes de exibir
                                df_display['Data'] = df_display['Data'].astype(str)
                                
                                st.dataframe(df_display.style.format({
                                    'Probabilidade_Acumulada': '{:.2f}%',
                                    'Probabilidade_Media_Movel': '{:.2f}%',
                                    'Probabilidade_Diaria': '{:.2f}%',
                                    'Total_Ocorrencias': '{:.0f}',
                                    'Total_Sucessos': '{:.0f}'
                                }))
                            
                        else:
                            st.warning(f"Não foram encontradas ocorrências suficientes da sequência '{sequencia_selecionada}' no período selecionado.")
                
                else:
                    st.info("Nenhuma sequência encontrada para análise temporal.")
            
            # Estatísticas avançadas
            st.markdown("---")
            st.subheader("📊 Estatísticas Avançadas por Categoria")
            
            col1, col2, col3 = st.columns(3)
            
            with col1:
                st.metric("🔄 Sequências Laterais", len(df_laterais))
                if not df_laterais.empty:
                    st.write(f"Mais comum: {df_laterais.iloc[0]['Sequência Anterior']}")
                    st.write(f"Ocorrências: {df_laterais.iloc[0]['Ocorrências']}")
            
            with col2:
                st.metric("🟢 Sequências Compradoras", len(df_compradoras))
                if not df_compradoras.empty:
                    st.write(f"Mais comum: {df_compradoras.iloc[0]['Sequência Anterior']}")
                    st.write(f"Ocorrências: {df_compradoras.iloc[0]['Ocorrências']}")
            
            with col3:
                st.metric("🔴 Sequências Vendedoras", len(df_vendedoras))
                if not df_vendedoras.empty:
                    st.write(f"Mais comum: {df_vendedoras.iloc[0]['Sequência Anterior']}")
                    st.write(f"Ocorrências: {df_vendedoras.iloc[0]['Ocorrências']}")
            
            # Recomendações baseadas nos dados
            st.markdown("---")
            st.subheader("💡 Insights e Recomendações")
            
            # Encontrar padrões fortes em cada categoria
            padroes_fortes_laterais = df_laterais[df_laterais['Viés'] != 'Neutro']
            padroes_fortes_compradoras = df_compradoras[df_compradoras['Viés'] == 'Comprador']
            padroes_fortes_vendedoras = df_vendedoras[df_vendedoras['Viés'] == 'Vendedor']
            
            col_rec1, col_rec2 = st.columns(2)
            
            with col_rec1:
                st.write("🎯 Padrões Fortes Identificados:")
                
                if not padroes_fortes_compradoras.empty:
                    melhor_compradora = padroes_fortes_compradoras.iloc[0]
                    st.success(f"*Comprador:* {melhor_compradora['Sequência Anterior']} → {melhor_compradora['Prob. Compradora (%)']}%")
                
                if not padroes_fortes_vendedoras.empty:
                    melhor_vendedora = padroes_fortes_vendedoras.iloc[0]
                    st.error(f"*Vendedor:* {melhor_vendedora['Sequência Anterior']} → {melhor_vendedora['Prob. Vendedora (%)']}%")
                
                if not padroes_fortes_laterais.empty:
                    melhor_lateral = padroes_fortes_laterais.iloc[0]
                    viés_cor = "🟢" if melhor_lateral['Viés'] == 'Comprador' else "🔴"
                    st.info(f"*Lateral {viés_cor}:* {melhor_lateral['Sequência Anterior']} → Comp: {melhor_lateral['Prob. Compradora (%)']}% | Vend: {melhor_lateral['Prob. Vendedora (%)']}%")
            
            with col_rec2:
                st.write("📈 Resumo por Categoria:")
                
                total_padroes = len(df_laterais) + len(df_compradoras) + len(df_vendedoras)
                if total_padroes > 0:
                    st.write(f"• *Laterais:* {len(df_laterais)} ({len(df_laterais)/total_padroes*100:.1f}%)")
                    st.write(f"• *Compradoras:* {len(df_compradoras)} ({len(df_compradoras)/total_padroes*100:.1f}%)")
                    st.write(f"• *Vendedoras:* {len(df_vendedoras)} ({len(df_vendedoras)/total_padroes*100:.1f}%)")
                    
                    # Viés geral do mercado
                    if len(df_compradoras) > len(df_vendedoras):
                        st.success("*Viés Geral:* Comprador")
                    elif len(df_vendedoras) > len(df_compradoras):
                        st.error("*Viés Geral:* Vendedor")
                    else:
                        st.info("*Viés Geral:* Neutro")