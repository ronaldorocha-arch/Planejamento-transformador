import streamlit as st
import pandas as pd
import math
from datetime import datetime, timedelta

# Configuração da página
st.set_page_config(page_title="Planejamento UPT - NHS", page_icon="⚡", layout="wide")

# --- 1. CONFIGURAÇÃO DE GIDs ---
GIDS = {
    "UPT-01": "1479604323",
    "UPT-02": "110648652",
    "UPT-03": "1141855262",
    "UPT-04": "910246264",
    "UPT-05": "1680061095",
    "UPT-06": "747234832",
    "UPT-07": "1486862820",
}

# Mapeamento: D=3(N1) até I=8(N6)
MAPA_N = {1: 3, 2: 4, 3: 5, 4: 6, 5: 7, 6: 8}

@st.cache_data(ttl=20)
def carregar_dados_upt(upt_nome):
    gid = GIDS.get(upt_nome, "0")
    url = f"https://docs.google.com/spreadsheets/d/1A5Rnbey8-kfXRdP7vOIq4rS3DTQlERHItsS1gbg53W0/export?format=csv&gid={gid}"
    try:
        df_raw = pd.read_csv(url, header=None, skiprows=2).astype(str)
        lista_modelos = []
        num_cols = df_raw.shape[1]
        for i in range(len(df_raw)):
            modelo = df_raw.iloc[i, 1].strip()
            desc = df_raw.iloc[i, 2].strip()
            if modelo != 'nan' and len(modelo) > 3:
                capacidades = {}
                for n_val, col_idx in MAPA_N.items():
                    if col_idx < num_cols:
                        val_str = df_raw.iloc[i, col_idx].replace(',', '.')
                        val = pd.to_numeric(val_str, errors='coerce')
                        capacidades[n_val] = val
                    else:
                        capacidades[n_val] = None
                lista_modelos.append({'ID': modelo, 'CAPACIDADES': capacidades, 'DISPLAY': f"{modelo} - {desc}"})
        return lista_modelos
    except:
        return None

def gerar_grade(h_ini_str, tem_gin):
    def p_min(h_s):
        h, m = map(int, h_s.split(':'))
        return h * 60 + m
    
    m_ini = p_min(h_ini_str)
    
    pausas_ocultas = [
        {"ini": "09:00", "fim": "09:10"}, 
        {"ini": "15:00", "fim": "15:10"}
    ]
    if tem_gin:
        pausas_ocultas.append({"ini": "09:30", "fim": "09:40"})
    
    pausa_visivel = {"nome": "🍱 ALMOÇO", "ini": "11:30", "fim": "12:30"}
    
    marcos_fixos = ["08:30", "09:30", "10:30", "11:30", "12:30", "13:30", "14:30", "15:30", "16:30", "17:30"]
    marcos_grade = sorted(list(set([h_ini_str] + [m for m in marcos_fixos if p_min(m) > m_ini])), key=p_min)
    
    grade = []
    for i in range(len(marcos_grade)-1):
        p1_s, p2_s = marcos_grade[i], marcos_grade[i+1]
        p1_m, p2_m = p_min(p1_s), p_min(p2_s)
        
        if p1_m >= p_min(pausa_visivel["ini"]) and p2_m <= p_min(pausa_visivel["fim"]):
            grade.append({'Horário': f"{p1_s} – {p2_s}", 'Minutos': 0, 'Label': pausa_visivel["nome"]})
        else:
            minutos_uteis = p2_m - p1_m
            for po in pausas_ocultas:
                po_ini, po_fim = p_min(po["ini"]), p_min(po["fim"])
                if p1_m < po_fim and p2_m > po_ini:
                    overlap = min(p2_m, po_fim) - max(p1_m, po_ini)
                    minutos_uteis -= overlap
            grade.append({'Horário': f"{p1_s} – {p2_s}", 'Minutos': max(0, minutos_uteis), 'Label': None})
    return grade

# --- INTERFACE ---
st.sidebar.markdown("### Tecnologia de Processos") # Adicionado aqui
st.sidebar.title("🏭 Planejamento UPT")
sel_upt = st.sidebar.selectbox("Setor", list(GIDS.keys()))
n_dia = st.sidebar.select_slider("Pessoas (N)", options=[1, 2, 3, 4, 5, 6], value=4)
h_inicio = st.sidebar.text_input("Início", "07:45")
tem_gin = st.sidebar.checkbox("Descontar Ginástica? (09:30)", value=False)

dados = carregar_dados_upt(sel_upt)

if dados:
    st.markdown("#### Tecnologia de Processos") # E adicionado aqui no corpo principal
    st.header(f"📋 Programação {sel_upt} | N={n_dia}")
    df_input = st.data_editor(pd.DataFrame(columns=["Modelo", "Quantidade"]), num_rows="dynamic", use_container_width=True,
        column_config={"Modelo": st.column_config.SelectboxColumn("Modelo", options=[m['DISPLAY'] for m in dados], required=True),
                       "Quantidade": st.column_config.NumberColumn("Qtd", min_value=1)}, key=f"ed_{sel_upt}")

    if st.button("🚀 GERAR PLANEJAMENTO"):
        if not df_input.empty:
            grade_slots = gerar_grade(h_inicio, tem_gin)
            fila = []
            erro_unidade = False
            for _, row in df_input.iterrows():
                if row['Modelo']:
                    m_obj = next(m for m in dados if m['DISPLAY'] == row['Modelo'])
                    uh = m_obj['CAPACIDADES'].get(n_dia)
                    
                    if pd.isna(uh) or uh is None or uh <= 0:
                        st.error(f"⚠️ ERRO: O modelo **{m_obj['ID']}** não possui Unidade/Hora cadastrada para **N={n_dia}** na planilha. Verifique a aba {sel_upt}.")
                        erro_unidade = True
                        break
                    
                    fila.append({'ID': m_obj['ID'], 'UH': uh, 'T_PC': 60 / uh, 'Qtd': row['Quantidade']})
            
            if not erro_unidade and fila:
                res, idx, acum, tot = [], 0, 0.0, 0
                total_pecas = sum(item['Qtd'] for item in fila)
                hora_termino = ""
                for s in grade_slots:
                    if s['Label']:
                        res.append({'Horário': s['Horário'], 'Modelos': s['Label'], 'Peças': 0, 'Acum.': tot})
                        continue
                    acum += s['Minutos']
                    p_bloco, mods_bloco = 0, []
                    while idx < len(fila):
                        item = fila[idx]
                        if acum >= (item['T_PC'] - 0.0001):
                            q = min(math.floor(acum / item['T_PC'] + 0.0001), item['Qtd'])
                            if q > 0:
                                acum -= (q * item['T_PC']); item['Qtd'] -= q
                                p_bloco += q; tot += q
                                info = f"{item['ID']} ({item['UH']} pç/h)"
                                if info not in mods_bloco: mods_bloco.append(info)
                            if tot >= total_pecas and hora_termino == "":
                                min_u = (s['Minutos'] - acum) if s['Minutos'] > acum else s['Minutos']
                                h_s, m_s = s['Horário'].split(' – ')[0].split(':')
                                dt_t = datetime.strptime(f"{h_s}:{m_s}", "%H:%M") + timedelta(minutes=min_u)
                                hora_termino = dt_t.strftime("%H:%M")
                            if item['Qtd'] <= 0: idx += 1
                            else: break
                        else: break
                    res.append({'Horário': s['Horário'], 'Modelos': " + ".join(mods_bloco) if mods_bloco else "-", 'Peças': int(p_bloco), 'Acum.': int(tot)})
                
                st.divider()
                c1, c2 = st.columns(2)
                c1.metric("Total", f"{tot} peças")
                c2.metric("Término", hora_termino if hora_termino else "Fora do turno")
                st.dataframe(pd.DataFrame(res), use_container_width=True)
else:
    st.warning("Verifique a planilha no Google Sheets.")
