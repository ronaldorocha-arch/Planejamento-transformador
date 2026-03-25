import streamlit as st
import pandas as pd
import math
from datetime import datetime, timedelta

# Configuração da página para NHS UPT
st.set_page_config(page_title="Planejamento UPT - NHS", page_icon="⚡", layout="wide")

# --- 1. CONFIGURAÇÃO DE GIDs (Extraídos dos seus links reais) ---
GIDS = {
    "UPT-01": "1479604323",
    "UPT-02": "110648652",
    "UPT-03": "1141855262",
    "UPT-04": "910246264",
    "UPT-05": "1680061095",
    "UPT-06": "747234832",
    "UPT-07": "1486862820",
}

# Mapeamento dinâmico conforme sua planilha (B=Modelo, C=Desc, D=N1...)
MAPA_N = {1: 3, 2: 4, 3: 5, 4: 6, 5: 7}

@st.cache_data(ttl=20)
def carregar_dados_upt(upt_nome):
    gid = GIDS.get(upt_nome, "0")
    # URL de exportação para CSV com base no GID selecionado
    url = f"https://docs.google.com/spreadsheets/d/1A5Rnbey8-kfXRdP7vOIq4rS3DTQlERHItsS1gbg53W0/export?format=csv&gid={gid}"
    try:
        # Pula as 2 primeiras linhas para iniciar na linha 3 dos dados
        df_raw = pd.read_csv(url, header=None, skiprows=2).astype(str)
        lista_modelos = []
        for i in range(len(df_raw)):
            modelo = df_raw.iloc[i, 1].strip()
            desc = df_raw.iloc[i, 2].strip()
            if modelo != 'nan' and len(modelo) > 3:
                # Captura capacidades para N de 1 a 5
                caps = {n: pd.to_numeric(df_raw.iloc[i, col], errors='coerce') for n, col in MAPA_N.items()}
                lista_modelos.append({'ID': modelo, 'CAPACIDADES': caps, 'DISPLAY': f"{modelo} - {desc}"})
        return lista_modelos
    except: return []

def gerar_grade(h_ini_str, tem_ginastica):
    def p_min(h_s):
        h, m = map(int, h_s.split(':'))
        return h * 60 + m

    m_ini = p_min(h_ini_str)
    m_alm_ini, m_alm_fim = p_min("11:30"), p_min("12:30")
    m_gin_ini, m_gin_fim = p_min("09:30"), p_min("09:40")
    
    # Marcadores de horas cheias para a tabela
    marcos = ["08:30", "09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30", "16:30", "17:30"]
    pontos = [h_ini_str] + [m for m in marcos if p_min(m) > m_ini]
    
    grade = []
    for i in range(len(pontos)-1):
        p1, p2 = p_min(pontos[i]), p_min(pontos[i+1])
        if p1 >= m_alm_ini and p2 <= m_alm_fim:
            grade.append({'Horário': f"{pontos[i]} – {pontos[i+1]}", 'Minutos': 0, 'Label': "🍱 ALMOÇO"})
        else:
            minutos_uteis = p2 - p1
            # Aplicação do desconto de Ginástica Laboral se ativa
            if tem_ginastica and p1 <= m_gin_ini < p2:
                minutos_uteis -= 10
            grade.append({'Horário': f"{pontos[i]} – {pontos[i+1]}", 'Minutos': minutos_uteis, 'Label': None})
    return grade

# --- INTERFACE LATERAL ---
st.sidebar.title("🏭 Planejamento UPT")
sel_upt = st.sidebar.selectbox("Selecionar Setor", list(GIDS.keys()))
n_dia = st.sidebar.select_slider("Quantidade de Pessoas (N)", options=[1, 2, 3, 4, 5], value=4)
h_inicio = st.sidebar.text_input("Início da Produção", "07:45")
tem_gin = st.sidebar.checkbox("Ginástica Laboral? (09:30 - 10min)", value=False)

dados = carregar_dados_upt(sel_upt)

if dados:
    st.header(f"📋 Programação {sel_upt} | N={n_dia}")
    
    # Editor de dados para entrada de Modelo e Quantidade
    df_input = st.data_editor(
        pd.DataFrame(columns=["Modelo", "Quantidade"]),
        num_rows="dynamic", use_container_width=True,
        column_config={
            "Modelo": st.column_config.SelectboxColumn("Modelo", options=[m['DISPLAY'] for m in dados], required=True),
            "Quantidade": st.column_config.NumberColumn("Qtd", min_value=1)
        }, key=f"ed_{sel_upt}"
    )

    if st.button("🚀 Gerar Planejamento"):
        if not df_input.empty:
            grade_slots = gerar_grade(h_inicio, tem_gin)
            fila, erro_unidade = [], False
            
            for _, row in df_input.iterrows():
                if row['Modelo']:
                    m_obj = next(m for m in dados if m['DISPLAY'] == row['Modelo'])
                    uh = m_obj['CAPACIDADES'].get(n_dia)
                    # Verifica se a Unidade/Hora está preenchida para o N selecionado
                    if pd.isna(uh) or uh <= 0:
                        st.error(f"❌ O modelo {m_obj['ID']} está sem Unidade/Hora para N={n_dia}!"); erro_unidade = True; break
                    fila.append({'ID': m_obj['ID'], 'UH': uh, 'T_PC': 60 / uh, 'Qtd': row['Quantidade']})
            
            if not erro_unidade:
                res, idx, acum, tot = [], 0, 0.0, 0
                total_pecas_total = sum(item['Qtd'] for item in fila)
                hora_final = ""

                for s in grade_slots:
                    if s['Label']:
                        res.append({'Horário': s['Horário'], 'Modelos': s['Label'], 'Unid/h': '-', 'Peças': 0, 'Acum.': tot})
                        continue
                    
                    acum += s['Minutos']
                    p_bloco, mods_bloco, uh_bloco = 0, [], []
                    
                    while idx < len(fila):
                        item = fila[idx]
                        if acum >= item['T_PC']:
                            q = min(math.floor(acum / item['T_PC']), item['Qtd'])
                            if q > 0:
                                acum -= (q * item['T_PC'])
                                item['Qtd'] -= q
                                p_bloco += q
                                tot += q
                                if item['ID'] not in mods_bloco: 
                                    mods_bloco.append(item['ID'])
                                    uh_bloco.append(f"{item['ID']}: {item['UH']}pç/h")
                            
                            # Cálculo preciso do horário de término
                            if tot >= total_pecas_total and hora_final == "":
                                minutos_gastos = s['Minutos'] - acum
                                h_ref, m_ref = s['Horário'].split(' – ')[0].split(':')
                                hora_final = (datetime.strptime(f"{h_ref}:{m_ref}", "%H:%M") + timedelta(minutes=minutos_gastos)).strftime("%H:%M")
                            
                            if item['Qtd'] <= 0: idx += 1
                            else: break
                        else: break
                    
                    res.append({
                        'Horário': s['Horário'], 
                        'Modelos': " + ".join(mods_bloco) if mods_bloco else "-", 
                        'Unid/h': " | ".join(uh_bloco) if uh_bloco else "-",
                        'Peças': int(p_bloco), 
                        'Acum.': int(tot)
                    })
                
                st.divider()
                # Exibição de Métricas no Topo
                c1, c2 = st.columns(2)
                c1.metric("Total Planejado", f"{tot} peças")
                c2.metric("Previsão de Término", hora_final if hora_final else "Além do horário")
                
                st.subheader("🗓️ Cronograma de Produção")
                st.dataframe(pd.DataFrame(res), use_container_width=True)
else:
    st.error("Planilha inacessível. Certifique-se de que o compartilhamento está como 'Qualquer pessoa com o link'!")
