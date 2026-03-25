import streamlit as st
import pandas as pd
import math
from datetime import datetime, timedelta

# Configuração da página
st.set_page_config(page_title="Planejamento UPT - NHS", page_icon="⚡", layout="wide")

# Dicionário de GIDs (ID de cada aba na sua planilha Google)
# ATENÇÃO: Verifique na URL da sua planilha o 'gid=' de cada aba e ajuste aqui
GIDS = {
    "UPT-01": "1479604323",
    "UPT-02": "0", # Exemplo: troque pelo ID real da aba
    "UPT-03": "0",
    "UPT-04": "0",
    "UPT-05": "0",
    "UPT-06": "0",
    "UPT-07": "0",
}

# Mapeamento das colunas de acordo com o N (Baseado na sua imagem 8282.png)
# B=1(Modelo), C=2(Desc), D=3(N1), E=4(N2), F=5(N3), G=6(N4), H=7(N5)
MAPA_N = {1: 3, 2: 4, 3: 5, 4: 6, 5: 7}

@st.cache_data(ttl=10)
def carregar_dados_upt(upt_nome):
    gid = GIDS.get(upt_nome, "0")
    url = f"https://docs.google.com/spreadsheets/d/1A5Rnbey8-kfXRdP7vOIq4rS3DTQlERHItsS1gbg53W0/export?format=csv&gid={gid}"
    try:
        # Lê a planilha pulando as 2 primeiras linhas (cabeçalho na linha 3)
        df_raw = pd.read_csv(url, header=None, skiprows=2).astype(str)
        lista_modelos = []
        
        for i in range(len(df_raw)):
            modelo = df_raw.iloc[i, 1].strip() # Coluna B
            desc = df_raw.iloc[i, 2].strip()   # Coluna C
            
            if modelo != 'nan' and len(modelo) > 2:
                # Criamos um dicionário com todas as capacidades de N1 a N5
                capacidades = {}
                for n_val, col_idx in MAPA_N.items():
                    val = pd.to_numeric(df_raw.iloc[i, col_idx], errors='coerce')
                    capacidades[n_val] = val
                
                lista_modelos.append({
                    'ID': modelo,
                    'DESCRICAO': desc,
                    'CAPACIDADES': capacidades,
                    'DISPLAY': f"{modelo} - {desc}"
                })
        return lista_modelos
    except Exception as e:
        st.error(f"Erro ao conectar com a aba {upt_nome}: {e}")
        return []

def gerar_grade_horaria(h_ini_str):
    def para_min(h_s):
        h, m = map(int, h_s.split(':'))
        return h * 60 + m

    m_ini = para_min(h_ini_str)
    m_almoco_ini = para_min("11:30")
    m_almoco_fim = para_min("12:30")
    
    # Pontos de quebra (horas cheias)
    marcos = ["08:30", "09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30", "16:30", "17:30"]
    pontos = [h_ini_str] + [m for m in marcos if para_min(m) > m_ini]
    
    grade = []
    for i in range(len(pontos)-1):
        p1, p2 = para_min(pontos[i]), para_min(pontos[i+1])
        if p1 == m_almoco_ini and p2 == m_almoco_fim:
            grade.append({'Horário': f"{pontos[i]} – {pontos[i+1]}", 'Minutos': 0, 'Label': "🍱 ALMOÇO"})
        else:
            # Descontar cafés (ajuste os horários se necessário)
            minutos = p2 - p1
            # Se o bloco contém o horário do café (ex: 09:00-09:10), subtrair 10 min
            grade.append({'Horário': f"{pontos[i]} – {pontos[i+1]}", 'Minutos': minutos, 'Label': None})
    return grade

# --- INTERFACE ---
st.sidebar.title("🏭 Planejamento UPT")
sel_upt = st.sidebar.selectbox("Selecionar Setor", list(GIDS.keys()))
n_selecionado = st.sidebar.select_slider("Quantidade de Pessoas (N)", options=[1, 2, 3, 4, 5], value=4)
h_inicio = st.sidebar.text_input("Início da Produção", "07:45")

# Carregar dados
dados_modelos = carregar_dados_upt(sel_upt)

if dados_modelos:
    st.header(f"📋 Programação {sel_upt} - (N={n_selecionado})")
    
    # Editor de modelos
    opcoes_display = [m['DISPLAY'] for m in dados_modelos]
    df_input = st.data_editor(
        pd.DataFrame(columns=["Modelo", "Quantidade"]),
        num_rows="dynamic",
        use_container_width=True,
        column_config={
            "Modelo": st.column_config.SelectboxColumn("Modelo", options=opcoes_display, required=True),
            "Quantidade": st.column_config.NumberColumn("Qtd", min_value=1)
        },
        key=f"editor_{sel_upt}"
    )

    if st.button("🚀 Gerar Cronograma"):
        if not df_input.empty:
            grade = gerar_grade_horaria(h_inicio)
            resultados = []
            
            # Preparar lista de processamento
            fila_producao = []
            erro_unidade = False
            
            for _, row in df_input.iterrows():
                if row['Modelo']:
                    # Busca o objeto do modelo
                    mod_obj = next(m for m in dados_modelos if m['DISPLAY'] == row['Modelo'])
                    unid_h = mod_obj['CAPACIDADES'].get(n_selecionado)
                    
                    if pd.isna(unid_h) or unid_h <= 0:
                        st.error(f"⚠️ O modelo **{mod_obj['ID']}** não tem Unidade/Hora cadastrada para N={n_selecionado} na planilha!")
                        erro_unidade = True
                        break
                    
                    fila_producao.append({
                        'ID': mod_obj['ID'],
                        'T_PC': 60 / unid_h,
                        'Qtd': row['Quantidade']
                    })
            
            if not erro_unidade:
                idx_fila = 0
                acum_min = 0.0
                tot_geral = 0
                
                for slot in grade:
                    if slot['Label']:
                        resultados.append({'Horário': slot['Horário'], 'Modelos': slot['Label'], 'Peças': 0})
                        continue
                    
                    acum_min += slot['Minutos']
                    p_no_bloco = 0
                    mods_no_bloco = []
                    
                    while idx_fila < len(fila_producao):
                        item = fila_producao[idx_fila]
                        if acum_min >= item['T_PC']:
                            q = min(math.floor(acum_min / item['T_PC']), item['Qtd'])
                            if q > 0:
                                acum_min -= (q * item['T_PC'])
                                item['Qtd'] -= q
                                p_no_bloco += q
                                tot_geral += q
                                mods_no_bloco.append(f"{item['ID']} ({int(q)}pç)")
                            
                            if item['Qtd'] <= 0:
                                idx_fila += 1
                            else:
                                break
                        else:
                            break
                    
                    resultados.append({
                        'Horário': slot['Horário'],
                        'Modelos': " + ".join(mods_no_bloco) if mods_no_bloco else "-",
                        'Peças': int(p_no_bloco)
                    })
                
                st.divider()
                st.subheader("🗓️ Cronograma Final")
                st.table(pd.DataFrame(resultados))
                st.success(f"Total planejado: {tot_geral} peças.")

else:
    st.warning("Selecione uma UPT e aguarde o carregamento dos modelos.")
