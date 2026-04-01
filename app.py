import streamlit as st
import pandas as pd
import math
import requests
from io import StringIO
from datetime import datetime, timedelta

# Configuração da página
st.set_page_config(page_title="Planejamento UPT - NHS", page_icon="⚡", layout="wide")

# --- 1. CONFIGURAÇÃO DE IDs e GIDs ---
# Usei o ID que você enviou e os GIDs das abas
ID_PLANILHA = "1A5Rnbey8-kfXRdP7vOIq4rS3DTQlERHItsS1gbg53W0"

GIDS = {
    "UPT-01": "1479604323",
    "UPT-02": "110648652",
    "UPT-03": "1141855262",
    "UPT-04": "910246264",
    "UPT-05": "1680061095",
    "UPT-06": "747234832",
    "UPT-07": "1486862820",
}

# Mapeamento das colunas de capacidade (N1=D, N2=E, N3=F, N4=G, N5=H, N6=I)
MAPA_N = {1: 3, 2: 4, 3: 5, 4: 6, 5: 7, 6: 8}

@st.cache_data(ttl=5)
def carregar_dados_upt(upt_nome):
    gid = GIDS.get(upt_nome)
    url = f"https://docs.google.com/spreadsheets/d/{ID_PLANILHA}/export?format=csv&gid={gid}"
    
    try:
        # Força o download usando requests para evitar erro de cache do pandas
        response = requests.get(url, timeout=10)
        if response.status_code != 200:
            return None
            
        # Lê o CSV ignorando as duas primeiras linhas de cabeçalho (skiprows=2)
        df_raw = pd.read_csv(StringIO(response.text), header=None, skiprows=2).astype(str)
        
        lista_modelos = []
        for i in range(len(df_raw)):
            modelo = df_raw.iloc[i, 1].strip() # Coluna B (Modelo)
            desc = df_raw.iloc[i, 2].strip()   # Coluna C (Descrição)
            
            if modelo != 'nan' and len(modelo) > 3:
                capacidades = {}
                for n_val, col_idx in MAPA_N.items():
                    if col_idx < df_raw.shape[1]:
                        val_str = df_raw.iloc[i, col_idx].replace(',', '.')
                        val = pd.to_numeric(val_str, errors='coerce')
                        capacidades[n_val] = val
                    else:
                        capacidades[n_val] = None
                
                lista_modelos.append({
                    'ID': modelo, 
                    'CAPACIDADES': capacidades, 
                    'DISPLAY': f"{modelo} - {desc}"
                })
        return lista_modelos
    except Exception as e:
        st.error(f"Erro na conexão: {e}")
        return None

def gerar_grade(h_ini_str, h_fim_str, tem_gin):
    def p_min(h_s):
        h, m = map(int, h_s.split(':'))
        return h * 60 + m
    
    m_ini, m_fim = p_min(h_ini_input), p_min(h_fim_input)
    pausas = [{"ini": "09:00", "fim": "09:10"}, {"ini": "15:00", "fim": "15:10"}]
    if tem_gin: pausas.append({"ini": "09:30", "fim": "09:40"})
    
    almoco = {"nome": "🍱 ALMOÇO", "ini": "11:30", "fim": "12:30"}
    marcos_base = ["08:30", "09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30", "16:30", "17:30"]
    marcos = sorted(list(set([h_ini_input, h_fim_input, almoco["ini"], almoco["fim"]] + 
                             [m for m in marcos_base if m_ini < p_min(m) < m_fim])))
    
    marcos = [m for m in marcos if m_ini <= p_min(m) <= m_fim]
    grade = []
    for i in range(len(marcos)-1):
        p1, p2 = marcos[i], marcos[i+1]
        m1, m2 = p_min(p1), p_min(p2)
        if m1 >= p_min(almoco["ini"]) and m2 <= p_min(almoco["fim"]):
            grade.append({'Horário': f"{p1} – {p2}", 'Minutos': 0, 'Label': almoco["nome"]})
        else:
            uteis = m2 - m1
            for po in pausas:
                o_i, o_f = p_min(po["ini"]), p_min(po["fim"])
                if m1 < o_f and m2 > o_i:
                    uteis -= (min(m2, o_f) - max(m1, o_i))
            grade.append({'Horário': f"{p1} – {p2}", 'Minutos': max(0, uteis), 'Label': None})
    return grade

# --- INTERFACE ---
st.sidebar.title("🏭 Planejamento UPT")
sel_upt = st.sidebar.selectbox("Setor", list(GIDS.keys()))
n_dia = st.sidebar.select_slider("Pessoas (N)", options=[1, 2, 3, 4, 5, 6], value=4)

h_ini_input = st.sidebar.text_input("Início Turno", "07:45")
h_fim_input = st.sidebar.text_input("Fim Turno", "17:30")
tem_gin = st.sidebar.checkbox("Descontar Ginástica?", value=False)

dados = carregar_dados_upt(sel_upt)

if dados:
    st.header(f"📋 Programação {sel_upt} | N={n_dia}")
    df_input = st.data_editor(pd.DataFrame(columns=["Modelo", "Quantidade"]), num_rows="dynamic", use_container_width=True,
        column_config={"Modelo": st.column_config.SelectboxColumn("Modelo", options=[m['DISPLAY'] for m in dados], required=True),
                       "Quantidade": st.column_config.NumberColumn("Qtd", min_value=1)}, key=f"ed_{sel_upt}")

    if st.button("🚀 GERAR PLANEJAMENTO"):
        if not df_input.empty:
            grade_slots = gerar_grade(h_ini_input, h_fim_input, tem_gin)
            fila = []
            for _, row in df_input.iterrows():
                if row['Modelo']:
                    m_obj = next(m for m in dados if m['DISPLAY'] == row['Modelo'])
                    uh = m_obj['CAPACIDADES'].get(n_dia)
                    if uh and uh > 0:
                        fila.append({'ID': m_obj['ID'], 'UH': uh, 'T_PC': 60 / uh, 'Qtd': row['Quantidade']})
            
            if fila:
                res, idx, acum, tot, h_term = [], 0, 0.0, 0, ""
                total_pecas = sum(item['Qtd'] for item in fila)
                
                for s in grade_slots:
                    if s['Label']:
                        res.append({'Horário': s['Horário'], 'Modelos': s['Label'], 'Peças': 0, 'Acum.': tot})
                        continue
                    
                    acum += s['Minutos']
                    p_bloco, mods = 0, []
                    while idx < len(fila):
                        item = fila[idx]
                        if acum >= (item['T_PC'] - 0.0001):
                            q = min(math.floor(acum / item['T_PC'] + 0.0001), item['Qtd'])
                            if q > 0:
                                acum -= (q * item['T_PC']); item['Qtd'] -= q
                                p_bloco += q; tot += q
                                mods.append(f"{int(q)}pç {item['ID']}")
                            if tot >= total_pecas and h_term == "":
                                h_s, m_s = s['Horário'].split(' – ')[0].split(':')
                                dt_t = datetime.strptime(f"{h_s}:{m_s}", "%H:%M") + timedelta(minutes=(s['Minutos']-acum))
                                h_term = dt_t.strftime("%H:%M")
                            if item['Qtd'] <= 0: idx += 1
                            else: break
                        else: break
                    res.append({'Horário': s['Horário'], 'Modelos': " + ".join(mods) if mods else "-", 'Peças': int(p_bloco), 'Acum.': int(tot)})
                
                st.divider()
                st.metric("Total Produzido", f"{int(tot)} peças", delta=f"Término: {h_term}")
                st.dataframe(pd.DataFrame(res), use_container_width=True)
else:
    st.error("⚠️ Erro ao carregar planilha. Verifique se ela está 'Publicada na Web' como CSV.")
