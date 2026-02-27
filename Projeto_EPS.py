import io
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date
import base64
import zipfile
import re

# =========================
# Configuração da página
# =========================
st.set_page_config(
    page_title="Dashboard EPS - Prefixos",
    page_icon="📊",
    layout="wide"
)

# Oculta menu, footer, barra superior do Streamlit Cloud e qualquer badge/link do GitHub
HIDE_DECORATIONS = """
<style>
#MainMenu {visibility: hidden;}
footer {visibility: hidden;}
div[data-testid="stToolbar"] {visibility: hidden; height: 0;}
div[data-testid="stStatusWidget"] {display: none;}
div[data-testid="stDecoration"] {display: none;}
.viewerBadge_link__qRh6M {display: none !important;}
a[href*="github.com"] {display: none !important;}
</style>
"""
st.markdown(HIDE_DECORATIONS, unsafe_allow_html=True)

# Defaults (UI x Cálculo)
# Defaults (UI x Cálculo base)
DEFAULT_DATA_LIMITE_UI = date(2026, 6, 30)     # o que APARECE para o usuário
DEFAULT_TOP_N = 44

# =========================
# Upload (apenas CSV) – ÚNICO ITEM DA SIDEBAR ANTES DO UPLOAD
# =========================
uploaded = st.sidebar.file_uploader("Faça upload do arquivo (CSV)", type=["csv"])

# Variáveis que serão definidas conforme o estado do upload
top_n = DEFAULT_TOP_N

# =========================
# Sidebar: controles adicionais SÓ APÓS O UPLOAD
# =========================
if uploaded is not None:
    st.sidebar.markdown("## 📌 Seções do Dashboard")
    st.sidebar.markdown("""
    <a href="#visao-geral" target="_self">📊 Visão Geral</a><br>
    <a href="#donut-eps" target="_self">🍩 Gráfico donut</a><br>
    <a href="#consulta-uor" target="_self">🔎 Consulta por UOR</a><br>
    <a href="#downloads" target="_self">⬇️ Downloads</a><br>
    <a href="#percentual-prefixo" target="_self">🏷️ Gráfico de barras</a><br>
    <a href="#meta-90" target="_self">🧮 Tabelas</a><br>
    """, unsafe_allow_html=True)

    # 👇 Data exibida (somente UI). Não será usada para cálculo.
    
    data_limite_ui = st.sidebar.date_input(
            "Data-limite estipulada",
            value=DEFAULT_DATA_LIMITE_UI,
            format="DD/MM/YYYY"
            # disabled=False  # deixe habilitado para o usuário poder mudar
    )

    top_n = st.sidebar.number_input(
        "Qtde. de Prefixos no gráfico", min_value=1, max_value=200,
        value=DEFAULT_TOP_N, step=1
    )
else:
    # Antes do upload, mantenha defaults
    data_limite_ui = DEFAULT_DATA_LIMITE_UI
    top_n = DEFAULT_TOP_N

# =========================
# Funções utilitárias
# =========================
COLS = ["Matricula", "Nome_Funcionario", "Avaliavel", "Data_Ultimo_Eps", "Situacao_Eps",
        "Dias_Para_Vencimento", "Status_Indicador", "Cargo", "Prefixo", "Dependencia",
        "Codigo_Uor", "Uor", "Prefixo_Ajure", "Ajure"]

def carregar_dados(file_like, encoding="utf-8", sep=","):
    df = pd.read_csv(file_like, header=None, names=COLS, encoding=encoding, sep=sep)
    return df

def preparar_df(df: pd.DataFrame):
    df["Data_Ultimo_Eps"] = pd.to_datetime(df["Data_Ultimo_Eps"], dayfirst=True, errors="coerce")
    return df

def download_button_base64(data_bytes: bytes, filename: str, label: str,
                           mime: str = "application/octet-stream",
                           key: str | None = None,
                           color: str = "#2e7d32",  # verde
                           color_hover: str = "#1b5e20") -> None:
    """
    Renderiza um botão de download (estilo Streamlit) usando data:URL base64.
    - data_bytes: conteúdo do arquivo em bytes
    - filename: nome sugerido para salvar
    - label: texto do botão (ex.: "Baixar Excel")
    - mime: content-type do arquivo (xlsx -> application/vnd.openxmlformats-officedocument.spreadsheetml.sheet)
    - key: id único opcional (se None, deriva do filename)
    - color/color_hover: personalização simples de cor
    """
    if not isinstance(data_bytes, (bytes, bytearray)):
        raise TypeError("data_bytes deve ser bytes/bytearray")

    b64 = base64.b64encode(data_bytes).decode("utf-8")
    href = f"data:{mime};base64,{b64}"

    # id único e válido para o CSS
    button_id = re.sub(r"[^a-zA-Z0-9_-]", "", (key or filename or "dl")).strip() or "dl"

    css = f"""
    <style>
      /* Botão base64 custom */
      #{button_id} {{
        background-color: {color};
        color: white;
        padding: 0.6rem 1rem;
        border: none;
        border-radius: 0.5rem;
        text-decoration: none;
        display: inline-block;
        font-weight: 600;
        cursor: pointer;
        transition: background-color 0.15s ease-in-out;
      }}
      #{button_id}:hover {{
        background-color: {color_hover};
        text-decoration: none;
      }}
    </style>
    """

    html = f'''
      {css}
      <a id="{button_id}" href="{href}" download="{filename}">{label}</a>
    '''
    st.markdown(html, unsafe_allow_html=True)
    
def mapear_para_2025(d_ui: date) -> date:
    """
    Recebe a data exibida (UI), normalmente em 2026,
    e retorna a MESMA data em 2025 (mesmo dia e mês).
    Se a data for 29/02, ajusta para 28/02/2025 (já que 2025 não é bissexto).
    """
    try:
        return date(2025, d_ui.month, d_ui.day)
    except ValueError:
        # Caso típico: 29/02 -> 28/02
        if d_ui.month == 2 and d_ui.day == 29:
            return date(2025, 2, 28)
        # Se quiser outra política (ex.: 01/03), troque a linha acima por:
        # return date(2025, 3, 1)
        raise

def donut_eps_plotly(
    porcentagem, 
    filtro_atual="Todos",
    cor_precisam="#e72914", 
    cor_nao_precisam="#0fe267"
):
    if filtro_atual == "Todos":
        filtro_texto = "Geral"
    else:
        filtro_texto = str(filtro_atual)

    fig = go.Figure(data=[go.Pie(
        labels=["Precisam fazer", f"Vencem até {data_limite_ui.strftime('%d/%m')}"],
        values=[porcentagem, 100 - porcentagem],
        hole=0.6,
        sort=False,
        direction="clockwise",
        marker=dict(colors=[cor_precisam, cor_nao_precisam], line=dict(color="#7c7c7c", width=2)),
        textfont_size=18,
        hoverinfo="label+percent"
    )])

    fig.update_layout(
        title=f"Percentual de pessoas que precisam fazer o EPS até {data_limite_ui.strftime('%d/%m/%Y')}",
        template="plotly_white",
        height=500,
        annotations=[
            dict(
                text=filtro_texto,
                x=0.5, y=0.5,
                showarrow=False,
                font=dict(size=30, color="#7c7c7c", family="Arial Black")
            )
        ],
        margin=dict(l=40, r=40, t=60, b=40)
    )
    return fig

def barras_prefixo_plotly_gradiente(
    porc_por_prefixo: pd.Series,
    top_n: int = 40,
    tema: str = "plotly_white",
    prefixo_destacar=None,
    ensure_visible: bool = True,
):
    serie = porc_por_prefixo.copy()

    def _label(x):
        return "NA" if pd.isna(x) else str(x)

    labels_series = pd.Series(serie.index, index=serie.index).apply(_label)

    top_n = max(1, int(top_n))
    base = serie.sort_values(ascending=True).tail(top_n)

    alvo_label = None
    if prefixo_destacar is not None and prefixo_destacar != "Todos":
        alvo_label = "NA" if (isinstance(prefixo_destacar, float) and pd.isna(prefixo_destacar)) or prefixo_destacar == "NA" \
                     else str(prefixo_destacar)

        if ensure_visible:
            match = labels_series[labels_series == alvo_label]
            if not match.empty:
                raw_idx = match.index[0]
                if raw_idx not in base.index:
                    base = pd.concat([base, serie.loc[[raw_idx]]])
                    base = base[~base.index.duplicated(keep="last")]
                    base = base.sort_values(ascending=True).tail(min(top_n, base.shape[0]))
            else:
                alvo_label = None
        else:
            labels_base = base.index.to_series().apply(_label)
            if alvo_label not in labels_base.values:
                alvo_label = None

    df_plot = pd.DataFrame({
        "Prefixo_raw": base.index,
        "Prefixo": base.index.to_series().apply(_label),
        "Porcentagem": base.values
    }).reset_index(drop=True)

    n = len(df_plot)
    altura = max(420, int(30 * n))

    fig = px.bar(
        df_plot,
        x="Porcentagem",
        y="Prefixo",
        orientation="h",
        color="Porcentagem",
        color_continuous_scale="Plasma_r",
        text="Porcentagem"
    )

    fig.update_layout(
        template=tema,
        height=altura,
        title=dict(text="Percentual pendente por Prefixo", x=0.5),
        xaxis=dict(
            title="Porcentagem",
            range=[0, 100],
            ticksuffix="%",
            showgrid=True,
            gridcolor="rgba(0,0,0,0.12)",
            gridwidth=1,
            zeroline=False
        ),
        yaxis=dict(
            title="Prefixo",
            categoryorder="array",
            categoryarray=df_plot["Prefixo"].tolist(),
            showgrid=True,
            gridcolor="rgba(0,0,0,0.08)",
            gridwidth=1
        ),
        bargap=0.25,
        margin=dict(l=90, r=150, t=60, b=40),
        coloraxis_colorbar=dict(title="%", ticksuffix="%"),
        showlegend=False
    )

    fig.update_traces(
        texttemplate="%{x:.1f}%",
        textposition="outside",
        cliponaxis=False
    )

    default_line = "#7c7c7c" if tema != "plotly_dark" else "rgba(255,255,255,0.6)"
    line_colors = [default_line] * n
    line_widths = [1.2] * n

    if alvo_label is not None:
        mask = (df_plot["Prefixo"] == alvo_label).values
        if mask.any():
            import numpy as _np
            pos = int(_np.flatnonzero(mask)[0])
            line_colors[pos] = "#00ff00"
            line_widths[pos] = 3

    fig.update_traces(marker_line_color=line_colors, marker_line_width=line_widths)
    return fig

def calcular_porcentagem_eps(dados: pd.DataFrame, dados_antes: pd.DataFrame, prefixo_escolhido=None):
    if prefixo_escolhido is None or prefixo_escolhido == "Todos":
        total = len(dados)
        qtd_antes = len(dados_antes)
    else:
        total = (dados["Prefixo"].astype(str) == str(prefixo_escolhido)).sum()
        qtd_antes = (dados_antes["Prefixo"].astype(str) == str(prefixo_escolhido)).sum()

    porcentagem = (qtd_antes / total * 100) if total > 0 else 0.0
    return porcentagem, total, qtd_antes

# =========================
# Conteúdo principal
# =========================
if uploaded is None:
    # Cabeçalho e descrição só aparecem antes do upload
    st.title("📊 Dashboard EPS - Análise por Data e Prefixo")
    st.markdown("""
    Este app lê os dados por prefixo, calcula o percentual de pessoas que **precisam fazer o EPS** (com base numa **data-limite**),
    e mostra:
    - Um **gráfico de donut** (vermelho/verde) com o percentual geral;
    - Um **gráfico de barras** com o percentual pendente por **Prefixo**.
    """)
    st.info("👆 Faça upload do dados para começar.")
    st.stop()

# === Daqui para baixo, SOMENTE quando há upload ===
try:
    if hasattr(uploaded, "seek"):
        uploaded.seek(0)
    dados = carregar_dados(uploaded, encoding="utf-8", sep=",")
except Exception as e:
    st.error(f"Erro ao carregar o CSV: {e}")
    st.stop()

if len(dados) == 0:
    st.error("O DataFrame está vazio após o carregamento/limpeza.")
    st.stop()

dados = preparar_df(dados)

# Data-limite de cálculo = MESMO dia/mês da UI, porém em 2025
data_limite_calc = mapear_para_2025(data_limite_ui)

# Timestamp usado para FILTRAR/CONTAR (cálculo real)
limite = pd.Timestamp(datetime.combine(data_limite_calc, datetime.min.time()))

# Filtrar "antes" (usa 2025!)
dados_antes = dados[dados["Data_Ultimo_Eps"] < limite].copy()

# Métricas gerais
total = len(dados)
qtd_antes = len(dados_antes)
porcentagem = (qtd_antes / total * 100) if total > 0 else 0.0

# --- Mapeamento Prefixo -> Dependência ---
tmp = (dados[["Prefixo", "Dependencia"]]
       .drop_duplicates(subset=["Prefixo"], keep="first"))

def _fmt_dep(x):
    if pd.isna(x) or str(x).strip() == "":
        return "NA"
    return str(x)

tmp["Dependencia_fmt"] = tmp["Dependencia"].apply(_fmt_dep)

prefixo_to_label = {}
for _, row in tmp.iterrows():
    pref_raw = row["Prefixo"]
    dep_fmt = row["Dependencia_fmt"]
    lbl = f"{'NA' if pd.isna(pref_raw) else str(pref_raw)} – {dep_fmt}"
    prefixo_to_label[pref_raw] = lbl

opcoes = ["Todos"]
opcoes += [prefixo_to_label[p] for p in sorted(tmp["Prefixo"].dropna().unique(), key=lambda x: str(x))]
if tmp["Prefixo"].isna().any():
    opcoes.append("NA – NA")

# Selectbox fica no corpo ou na sidebar?
# Mantive na sidebar, MAS ele só existe após upload (sidebar já está condicional)
escolha = st.sidebar.selectbox("Filtrar/Destacar por Prefixo – Dependencia", opcoes, index=0)

if escolha == "Todos":
    prefixo_escolhido = "Todos"
elif escolha.startswith("NA"):
    prefixo_escolhido = "NA"
else:
    prefixo_escolhido = escolha.split(" – ")[0]

valor_filtro = None if prefixo_escolhido == "Todos" else prefixo_escolhido

# Percentuais para donut conforme filtro
if valor_filtro == "NA":
    dados_filtrados = dados[dados["Prefixo"].isna()]
    dados_antes_filtrados = dados_antes[dados_antes["Prefixo"].isna()]
    porcentagem, total, qtd_antes = calcular_porcentagem_eps(dados_filtrados, dados_antes_filtrados, prefixo_escolhido="NA")
elif valor_filtro is None:
    porcentagem, total, qtd_antes = calcular_porcentagem_eps(dados, dados_antes, prefixo_escolhido=None)
else:
    porcentagem, total, qtd_antes = calcular_porcentagem_eps(dados, dados_antes, prefixo_escolhido=valor_filtro)

# --- KPIs ---
st.markdown('<a name="visao-geral"></a>', unsafe_allow_html=True)
st.divider()
st.subheader("Visão geral")
c1, c2, c3 = st.columns(3)
rotulo = "Todos" if valor_filtro is None else ("(NA)" if valor_filtro == "NA" else str(valor_filtro))
c1.metric(f"Total de registros – {rotulo}", f"{total:,}".replace(",", "."))
c2.metric(f"Quantidade de pessoas pendentes {data_limite_ui.strftime('%d/%m')}", f"{qtd_antes:,}".replace(",", "."))
c3.metric("Percentual pendente", f"{porcentagem:.1f}%")

# ===== Gráfico de Donut =====
st.markdown('<a name="donut-eps"></a>', unsafe_allow_html=True)
st.divider()
st.subheader("🍩 Percentual geral")
fig_donut = donut_eps_plotly(
    porcentagem,
    filtro_atual=prefixo_escolhido,
    cor_precisam="#e72914",
    cor_nao_precisam="#0fe267"
)
st.plotly_chart(
    fig_donut,
    use_container_width=True,
    config={
        "toImageButtonOptions": {"format": "png", "filename": "donut_eps", "scale": 2},
        "displaylogo": False
    }
)

st.markdown('<a name="consulta-uor"></a>', unsafe_allow_html=True)
st.divider()
st.subheader("🔎 Consultar pendências por UOR (Prefixo 8553)")

def _sanitize_sheet_title(s: str) -> str:
    invalid = set('\\/:*?[]:"<>|')
    out = "".join("_" if ch in invalid else ch for ch in (s or "").strip())
    out = " ".join(out.split())
    out = out[:31] if out else "Pendentes"
    return out

def _sanitize_filename(s: str) -> str:
    invalid = set('\\/:*?[]:"<>|')
    out = "".join("_" if ch in invalid else ch for ch in (s or "").strip())
    out = " ".join(out.split())
    return out or "Pendentes"

def _fmt_uor(x):
    return "NA" if pd.isna(x) or str(x).strip() == "" else str(x)

mask_pref_8553 = (dados["Prefixo"].astype(str) == "8553")
uors_8553 = dados.loc[mask_pref_8553, "Uor"]

if uors_8553.empty:
    st.warning("Não há UORs cadastradas para o Prefixo 8553 nos dados carregados.")
else:
    uors_unicas = sorted({_fmt_uor(x) for x in uors_8553.unique()})

    uor_escolhida = st.selectbox(
        "Selecione a UOR (apenas Prefixo 8553)",
        options=uors_unicas,
        index=0,
        help="Digite para buscar e selecione a UOR desejada (apenas UORs do Prefixo 8553)."
    )

    mask_pend_pref = (dados_antes["Prefixo"].astype(str) == "8553")
    if uor_escolhida == "NA":
        mask_pend_uor = dados_antes["Uor"].isna()
    else:
        mask_pend_uor = (dados_antes["Uor"].astype(str) == uor_escolhida)

    df_uor_pend = dados_antes[mask_pend_pref & mask_pend_uor].copy()

    c1, c2, c3 = st.columns(3)
    c1.metric("Prefixo", "8553")
    c2.metric("UOR selecionada", uor_escolhida)
    c3.metric("Pendências na UOR", f"{len(df_uor_pend):,}".replace(",", "."))

    st.dataframe(df_uor_pend, use_container_width=True)

    nome_base = _sanitize_filename(f"{uor_escolhida} Pendentes")
    sheet_title = _sanitize_sheet_title(uor_escolhida)

    try:
        buf_xlsx = io.BytesIO()
        with pd.ExcelWriter(buf_xlsx, engine="openpyxl") as writer:
            df_uor_pend.to_excel(writer, sheet_name=sheet_title, index=False)
        buf_xlsx.seek(0)
        st.download_button(
            label="📗 Baixar Excel (UOR selecionada)",
            data=buf_xlsx,
            file_name=f"{nome_base}.xlsx",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            use_container_width=True
        )
    except Exception as e:
        st.error(f"Erro ao gerar Excel da UOR: {e}")

st.markdown('<a name="downloads"></a>', unsafe_allow_html=True)
st.divider()
st.subheader("⬇️ Baixar dados das pendências")

col1, col2 = st.columns(2)

cols_to_drop = ["Situacao_Eps", "Status_Indicador"]

with col1:
    st.caption("Excel com uma planilha por Prefixo (apenas pendentes).")
    try:
        # --- Gera o Excel multi-aba em memória ---
        buf_xlsx_multi = io.BytesIO()
        with pd.ExcelWriter(buf_xlsx_multi, engine="openpyxl") as writer:
            for pref, grp in dados_antes.groupby("Prefixo", dropna=False):
                sheet = "NA" if pd.isna(pref) else str(pref)[:31]
                grp_export = grp.drop(columns=cols_to_drop, errors="ignore")
                grp_export.to_excel(writer, sheet_name=sheet, index=False)

        xlsx_bytes_multi = buf_xlsx_multi.getvalue()

        # Opcional: validação do conteúdo (xlsx é um ZIP, começa com 'PK')
        # st.write("Multi-aba bytes:", len(xlsx_bytes_multi), "Header:", xlsx_bytes_multi[:2])

        # Depois que você gerar xlsx_bytes_multi...
        download_button_base64(
            data_bytes=xlsx_bytes_multi,
            filename="dados_pendentes_por_prefixo.xlsx",
            label="📘 Baixar Excel (1 aba por Prefixo)",
            mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            key="dl_por_prefixo_btn",
            color="#2962ff",        # azul (opcional)
            color_hover="#0039cb"   # azul escuro (opcional)
        )
    except Exception as e:
        st.error(f"Erro ao gerar Excel por Prefixo: {e}")

with col2:
    st.caption("Excel único (uma aba) com todas as pendências.")
    try:
        buf_xlsx_single = io.BytesIO()
        with pd.ExcelWriter(buf_xlsx_single, engine="openpyxl") as writer:
            dados_pend_export = dados_antes.drop(columns=cols_to_drop, errors="ignore")
            dados_pend_export.to_excel(writer, sheet_name="Pendentes", index=False)

        xlsx_bytes_single = buf_xlsx_single.getvalue()
        # st.write("Uma-aba bytes:", len(xlsx_bytes_single), "Header:", xlsx_bytes_single[:2])

        st.download_button(
            label="📗 Baixar Excel (uma aba)",
            data=xlsx_bytes_single,
            file_name="dados_pendentes.xlsx",
            mime="application/octet-stream",  # <- genérico, ajuda evitar progress.htm
            use_container_width=True,
            key="download_uma_aba_v2"
        )

        # # ZIP fallback
        # with io.BytesIO() as zip_buf:
        #     with zipfile.ZipFile(zip_buf, mode="w", compression=zipfile.ZIP_DEFLATED) as zf:
        #         zf.writestr("dados_pendentes.xlsx", xlsx_bytes_single)
        #     zip_bytes_single = zip_buf.getvalue()

        # st.download_button(
        #     label="📦 (Fallback) Baixar ZIP com o Excel (uma aba)",
        #     data=zip_bytes_single,
        #     file_name="dados_pendentes.zip",
        #     mime="application/zip",
        #     use_container_width=True,
        #     key="download_uma_aba_zip"
        # )

        # # Base64 link fallback
        # b64_single = base64.b64encode(xlsx_bytes_single).decode("utf-8")
        # href_single = (
        #     f'<a download="dados_pendentes.xlsx" '
        #     f'href="data:application/octet-stream;base64,{b64_single}">⬇️ Baixar (via link base64)</a>'
        # )
        # st.markdown(href_single, unsafe_allow_html=True)

    except Exception as e:
        st.error(f"Erro ao gerar Excel único: {e}")

# ===== Percentual por Prefixo =====
st.markdown('<a name="percentual-prefixo"></a>', unsafe_allow_html=True)
st.divider()
st.subheader("🏷️ Percentual por Prefixo")

if "Prefixo" not in dados.columns:
    st.error("Coluna 'Prefixo' não encontrada no CSV.")
    st.stop()

totais = dados["Prefixo"].value_counts()
antes = dados_antes["Prefixo"].value_counts()
porc_por_prefixo = (antes / totais * 100).fillna(0).sort_index()

fig_barras = barras_prefixo_plotly_gradiente(
    porc_por_prefixo=porc_por_prefixo,
    top_n=top_n,
    tema="plotly_white",
    prefixo_destacar=None if prefixo_escolhido == "Todos" else prefixo_escolhido,
    ensure_visible=True
)
st.plotly_chart(
    fig_barras,
    use_container_width=True,
    config={
        "toImageButtonOptions": {"format": "png", "filename": "barras_prefixo", "scale": 2},
        "displaylogo": False
    }
)

st.divider()

# ===== Tabelas auxiliares =====
with st.expander("📋 Tabela: Percentual pendente por Prefixo"):
    st.dataframe(porc_por_prefixo.round(2).rename("Porcentagem (%)"), use_container_width=True)

st.markdown('<a name="meta-90"></a>', unsafe_allow_html=True)
with st.expander("🧮 Tabelas de contagem (totais e pendentes)"):
    col_a, col_b = st.columns(2)
    col_a.write("**Totais por Prefixo**")
    col_a.dataframe(totais.rename("Total"), use_container_width=True)
    col_b.write("**Pendentes por Prefixo**")
    col_b.dataframe(antes.rename("Pendentes"), use_container_width=True)

    st.markdown("### 📌 Meta: **90% pendentes** por Prefixo")
    meta_pct = 0.90

    idx = sorted(totais.index.union(antes.index), key=lambda x: str(x))
    dfm = pd.DataFrame(index=idx)
    dfm["Total"] = totais.reindex(idx).fillna(0).astype(int)
    dfm["Pendentes"] = antes.reindex(idx).fillna(0).astype(int)
    dfm["%Pendentes"] = (dfm["Pendentes"] / dfm["Total"] * 100).replace([np.inf, -np.inf], 0).fillna(0)

    metodo = st.radio(
        "Como calcular a coluna **Faltam para 90%**?",
        ["Arredondado", "Compensado (maior resto)"],
        horizontal=True
    )

    dfm["Meta_90%_Qtd"] = np.ceil(meta_pct * dfm["Total"]).astype(int)
    dfm["Faltam_Ceil"] = (dfm["Meta_90%_Qtd"] - dfm["Pendentes"]).clip(lower=0).astype(int)

    if metodo == "Arredondado":
        df_out = dfm[["Total", "Pendentes", "%Pendentes", "Meta_90%_Qtd", "Faltam_Ceil"]].rename(
            columns={"Faltam_Ceil": "Faltam para 90% (ceil)"}
        )
    else:
        ideal = meta_pct * dfm["Total"] - dfm["Pendentes"]
        ideal_pos = ideal.clip(lower=0)
        base = np.floor(ideal_pos).astype(int)
        resto = (ideal_pos - base)
        total_target = int(round(ideal_pos.sum()))
        to_allocate = max(0, total_target - int(base.sum()))
        extra = pd.Series(0, index=dfm.index, dtype=int)
        if to_allocate > 0:
            ordem = resto.sort_values(ascending=False).index.tolist()
            for i, idx_pref in enumerate(ordem):
                if i >= to_allocate:
                    break
                extra.loc[idx_pref] += 1
        faltam_comp = (base + extra).astype(int).clip(lower=0)

        df_out = dfm[["Total", "Pendentes", "%Pendentes"]].copy()
        df_out["Meta_90%_Qtd (compensado)"] = (df_out["Pendentes"] + faltam_comp).astype(int)
        df_out["Faltam para 90% (compensado)"] = faltam_comp.astype(int)

    if metodo == "Arredondado":
        faltam_col = "Faltam para 90% (ceil)"
        meta_col = "Meta_90%_Qtd"
    else:
        faltam_col = "Faltam para 90% (compensado)"
        meta_col = "Meta_90%_Qtd (compensado)"

    total_geral = df_out["Total"].sum()
    pendentes_atuais = df_out["Pendentes"].sum()
    faltam_total = df_out[faltam_col].sum()

    pendentes_finais = pendentes_atuais + faltam_total
    pct_final = pendentes_finais / total_geral * 100 if total_geral > 0 else 0

    st.dataframe(
        df_out.style.format({"%Pendentes": "{:.1f}%"}),
        use_container_width=True
    )

st.info("""
**Observações**
- Entrada **somente CSV**.
""")