import io
import pandas as pd
import numpy as np
import streamlit as st
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, date

# =========================
# Configuração da página
# =========================
# def gatekeeper_password():
#     """
#     Porta de entrada por senha única:
#     - Se já autenticado, libera o app.
#     - Se não, mostra um formulário de senha com mensagens amigáveis.
#     - Sempre interrompe a execução (st.stop) enquanto não autenticado.
#     """
#     # Já autenticado nesta sessão?
#     if st.session_state.get("auth_ok", False):
#         return

#     # Verifica se a senha foi configurada em st.secrets
#     senha_configurada = st.secrets.get("PASSWORD", None)
#     if not senha_configurada:
#         st.title("🔒 Acesso restrito")
#         st.error(
#             "Configuração ausente: a senha do app não foi definida.\n\n"
#             "Peça ao responsável pelo deploy para configurar **`PASSWORD`** em *Settings → Secrets*."
#         )
#         st.stop()

#     # Controle simples de tentativas (opcional)
#     if "login_tries" not in st.session_state:
#         st.session_state.login_tries = 0

#     st.title("🔒 Acesso restrito")

#     with st.form("form_login", clear_on_submit=False):
#         pwd = st.text_input("Informe a senha", type="password", help="Acesso permitido apenas a usuários autorizados.")
#         entrar = st.form_submit_button("Entrar")

#     if entrar:
#         if not pwd:
#             st.warning("Digite a senha para continuar.")
#         elif pwd == senha_configurada:
#             st.session_state["auth_ok"] = True
#             st.session_state.login_tries = 0
#             st.success("Acesso liberado! Carregando o dashboard…")
#             st.rerun()
#         else:
#             st.session_state.login_tries += 1
#             # Mensagens amigáveis sem código/trace
#             if st.session_state.login_tries == 1:
#                 st.error("Senha incorreta. Tente novamente.")
#             elif st.session_state.login_tries < 5:
#                 st.error(f"Senha incorreta. Tentativas: {st.session_state.login_tries}/5.")
#                 st.caption("Dica: verifique maiúsculas/minúsculas ou copie/cole a senha com cuidado.")
#             else:
#                 st.error("Muitas tentativas falhas. Aguarde um momento e tente novamente.")
#                 st.caption("Se o problema persistir, contate o responsável pelo dashboard.")

#     # Enquanto não autenticado, interrompe o app aqui
#     st.stop()

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

# gatekeeper_password()  # <- chama antes do restante do app

# -- Upload (apenas CSV) --
uploaded = st.sidebar.file_uploader("Faça upload do arquivo (CSV)", type=["csv"])

# -- Cabeçalho e descrição só aparecem antes do upload --
if uploaded is None:
    st.title("📊 Dashboard EPS - Análise por Data e Prefixo")
    st.markdown("""
    Este app lê os dados por prefixo, calcula o percentual de pessoas que **precisam fazer o EPS** (com base numa **data-limite**),
    e mostra:
    - Um **gráfico de donut** (vermelho/verde) com o percentual geral;
    - Um **gráfico de barras** com o percentual pendente por **Prefixo**.
    """)

# Opções de leitura
#drop_first_line = st.sidebar.checkbox("Remover o cabeçalho extra (apenas se necessário)", value=False)
st.sidebar.markdown("## 📌 Seções do Dashboard")
st.sidebar.markdown("""
<a href="#visao-geral" target="_self">📊 Visão Geral</a><br>
<a href="#donut-eps" target="_self">🍩 Donut EPS</a><br>
<a href="#consulta-uor" target="_self">🔎 Consulta por UOR</a><br>
<a href="#percentual-prefixo" target="_self">🏷️ Percentual por Prefixo</a><br>
<a href="#meta-90" target="_self">🧮 Meta de 90%</a><br>
<a href="#downloads" target="_self">⬇️ Downloads</a>
""", unsafe_allow_html=True)
# Data-limite (default: 30/06/2025)
data_limite = st.sidebar.date_input(
    "Data-limite (registros **antes** desta data precisam fazer o EPS)",
    value=date(2025, 6, 30),
    format="DD/MM/YYYY"
)

# Top N prefixos no gráfico de barras
top_n = st.sidebar.number_input("Qtde. de Prefixos no gráfico", min_value=1, max_value=200, value=44, step=1)

# Cores do donut: primeira fatia = "precisam", segunda = "não precisam"
st.sidebar.subheader("🎨 Cores do gráfico de donut")
cor_precisam = st.sidebar.color_picker("Cor para **quem precisa**", value="#e72914")   # vermelho
cor_nao_precisam = st.sidebar.color_picker("Cor para **quem não precisa**", value="#0fe267")  # verde

# =========================
# Funções utilitárias
# =========================
COLS = ["Matricula", "Nome_Funcionario", "Avaliavel", "Data_Ultimo_Eps", "Situacao_Eps",
        "Dias_Para_Vencimento", "Status_Indicador", "Cargo", "Prefixo", "Dependencia",
        "Codigo_Uor", "Uor", "Prefixo_Ajure", "Ajure"]

def carregar_dados(file_like, encoding="utf-8", sep=","):
    # Mantém sua estrutura de nomes fixos, sem remover linhas
    df = pd.read_csv(file_like, header=None, names=COLS, encoding=encoding, sep=sep)
    return df

def preparar_df(df: pd.DataFrame):
    # Converte coluna de data (dia/mês/ano)
    df["Data_Ultimo_Eps"] = pd.to_datetime(df["Data_Ultimo_Eps"], dayfirst=True, errors="coerce")
    return df

def donut_eps_plotly(
    porcentagem, 
    filtro_atual="Todos",
    cor_precisam="#e72914", 
    cor_nao_precisam="#0fe267"
):
    # Converte filtro para texto amigável
    if filtro_atual == "Todos":
        filtro_texto = "Geral"
    else:
        filtro_texto = str(filtro_atual)

    fig = go.Figure(data=[go.Pie(
        labels=["Precisam fazer", f"Vencem até {data_limite.strftime('%d/%m')}"],
        values=[porcentagem, 100 - porcentagem],
        hole=0.6,
        sort=False,
        direction="clockwise",
        marker=dict(colors=[cor_precisam, cor_nao_precisam], line=dict(color="#7c7c7c", width=2)),
        #textinfo="none",   # <<<<<< TIRA PORCENTAGENS DAS FATIAS
        textfont_size=18,
        hoverinfo="label+percent"
    )])

    fig.update_layout(
        title=f"Percentual de pessoas que precisam fazer o EPS até {data_limite.strftime('%d/%m/%Y')}",
        template="plotly_white",
        height=500,

        # Apenas o nome do filtro no centro
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
    """
    Barras horizontais com degradê Plasma_r + grid,
    destacando o prefixo selecionado com contorno.
    """
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
            line_colors[pos] = "#00ff00"  # destaque vermelho
            line_widths[pos] = 3

    fig.update_traces(marker_line_color=line_colors, marker_line_width=line_widths)
    return fig

def calcular_porcentagem_eps(dados: pd.DataFrame, dados_antes: pd.DataFrame, prefixo_escolhido=None):
    """
    Retorna (porcentagem, total, qtd_antes) considerando:
      - Geral (prefixo_escolhido is None ou 'Todos')
      - Ou apenas um prefixo específico.
    """
    if prefixo_escolhido is None or prefixo_escolhido == "Todos":
        total = len(dados)
        qtd_antes = len(dados_antes)
    else:
        total = (dados["Prefixo"].astype(str) == str(prefixo_escolhido)).sum()
        qtd_antes = (dados_antes["Prefixo"].astype(str) == str(prefixo_escolhido)).sum()

    porcentagem = (qtd_antes / total * 100) if total > 0 else 0.0
    return porcentagem, total, qtd_antes

# =========================
# Pipeline principal
# =========================
if uploaded is None:
    st.info("👆 Faça upload do dados para começar.")
else:
    try:
        # Garante que o ponteiro está no início (caso tenha sido lido antes em outro lugar)
        if hasattr(uploaded, "seek"):
            uploaded.seek(0)

        dados = carregar_dados(uploaded, encoding="utf-8", sep=",")
        #if drop_first_line:
            #dados = dados.drop(index=0).reset_index(drop=True)
    except Exception as e:
        st.error(f"Erro ao carregar o CSV: {e}")
        st.stop()


    # Pré-visualização
    with st.expander("🔎 Pré-visualização dos dados (primeiras linhas)"):
        st.dataframe(dados.head(20), use_container_width=True)

    if len(dados) == 0:
        st.error("O DataFrame está vazio após o carregamento/limpeza.")
        st.stop()

    # Preparar DF
    dados = preparar_df(dados)

    # Data-limite
    limite = pd.Timestamp(datetime.combine(data_limite, datetime.min.time()))

    # Filtrar "antes"
    dados_antes = dados[dados["Data_Ultimo_Eps"] < limite].copy()

    # Métricas gerais
    total = len(dados)
    qtd_antes = len(dados_antes)
    porcentagem = (qtd_antes / total * 100) if total > 0 else 0.0

    # --- Construção do mapeamento Prefixo -> Dependencia (primeira não nula) ---
    tmp = (dados[["Prefixo", "Dependencia"]]
        .drop_duplicates(subset=["Prefixo"], keep="first"))

    def _fmt_dep(x):
        if pd.isna(x) or str(x).strip() == "":
            return "NA"
        return str(x)

    tmp["Dependencia_fmt"] = tmp["Dependencia"].apply(_fmt_dep)

    prefixo_to_label = {}
    for _, row in tmp.iterrows():
        pref_raw = row["Prefixo"]             # mantém tipo original (int/float/str ou NaN)
        dep_fmt = row["Dependencia_fmt"]
        lbl = f"{'NA' if pd.isna(pref_raw) else str(pref_raw)} – {dep_fmt}"
        prefixo_to_label[pref_raw] = lbl

    # Opções: "Todos" + prefixos não nulos (sem converter para str aqui!)
    opcoes = ["Todos"]
    opcoes += [prefixo_to_label[p] 
            for p in sorted(tmp["Prefixo"].dropna().unique(), key=lambda x: str(x))]

    # Se existir prefixo nulo:
    if tmp["Prefixo"].isna().any():
        opcoes.append("NA – NA")

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
    c1, c2, c3 = st.columns(3)
    rotulo = "Todos" if valor_filtro is None else ("(NA)" if valor_filtro == "NA" else str(valor_filtro))
    c1.metric(f"Total de registros – {rotulo}", f"{total:,}".replace(",", "."))
    c2.metric(f"Quantidade de pessoas pendentes {data_limite.strftime('%d/%m/%Y')}", f"{qtd_antes:,}".replace(",", "."))
    c3.metric("Percentual pendente", f"{porcentagem:.1f}%")

    # ===== Gráfico de Donut =====
    st.markdown('<a name="donut-eps"></a>', unsafe_allow_html=True)
    st.subheader("🍩 Percentual geral")
    fig_donut = donut_eps_plotly(
    porcentagem,
    filtro_atual=prefixo_escolhido,   # 👈 agora mostra o filtro selecionado
    cor_precisam=cor_precisam,
    cor_nao_precisam=cor_nao_precisam)
    st.plotly_chart(
        fig_donut,
        use_container_width=True,
        config={
            "toImageButtonOptions": {"format": "png", "filename": "donut_eps", "scale": 2},
            "displaylogo": False
        }
    )

    st.divider()
    st.markdown('<a name="consulta-uor"></a>', unsafe_allow_html=True)
    st.subheader("🔎 Consultar pendências por UOR (Prefixo 8553)")

    # Helpers de sanitização para Excel
    def _sanitize_sheet_title(s: str) -> str:
        # Excel sheet name: sem \ / ? * [ ] : " < > | e máx 31 chars
        invalid = set('\\/:*?[]:"<>|')
        out = "".join("_" if ch in invalid else ch for ch in (s or "").strip())
        out = " ".join(out.split())  # normaliza espaços
        out = out[:31] if out else "Pendentes"  # limite + fallback
        return out

    def _sanitize_filename(s: str) -> str:
        # Evita caracteres proibidos em nomes de arquivo (Win/macOS)
        invalid = set('\\/:*?[]:"<>|')
        out = "".join("_" if ch in invalid else ch for ch in (s or "").strip())
        out = " ".join(out.split())
        return out or "Pendentes"

    # 1) Coleta UORs apenas do Prefixo 8553 (base completa, não só pendentes)
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

        # 2) Filtra pendências (dados_antes) por Prefixo 8553 + UOR escolhida
        mask_pend_pref = (dados_antes["Prefixo"].astype(str) == "8553")
        if uor_escolhida == "NA":
            mask_pend_uor = dados_antes["Uor"].isna()
        else:
            mask_pend_uor = (dados_antes["Uor"].astype(str) == uor_escolhida)

        df_uor_pend = dados_antes[mask_pend_pref & mask_pend_uor].copy()

        # 3) KPIs + tabela
        c1, c2, c3 = st.columns(3)
        c1.metric("Prefixo", "8553")
        c2.metric("UOR selecionada", uor_escolhida)
        c3.metric("Pendências na UOR", f"{len(df_uor_pend):,}".replace(",", "."))

        st.dataframe(df_uor_pend, use_container_width=True)

        # 4) Download apenas Excel, com nome "<UOR> Pendentes.xlsx"
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

    st.divider()
    st.markdown('<a name="downloads"></a>', unsafe_allow_html=True)
    st.subheader("⬇️ Baixar dados das pendências")

    col1, col2 = st.columns(2)

    # 1) Excel com uma aba por Prefixo (apenas pendentes)
    with col1:
        st.caption("Excel com uma planilha por Prefixo (apenas pendentes).")
        try:
            buf_xlsx_multi = io.BytesIO()
            with pd.ExcelWriter(buf_xlsx_multi, engine="openpyxl") as writer:
                for pref, grp in dados_antes.groupby("Prefixo", dropna=False):
                    sheet = "NA" if pd.isna(pref) else str(pref)[:31]
                    grp.to_excel(writer, sheet_name=sheet, index=False)
            buf_xlsx_multi.seek(0)
            st.download_button(
                label="📘 Baixar Excel (1 aba por Prefixo)",
                data=buf_xlsx_multi,
                file_name="dados_pendentes_por_prefixo.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Erro ao gerar Excel por Prefixo: {e}")

    # 2) CSV único com todas as pendências
    with col2:
        st.caption("Excel único (uma aba) com todas as pendências.")
        try:
            buf_xlsx_single = io.BytesIO()
            with pd.ExcelWriter(buf_xlsx_single, engine="openpyxl") as writer:
                dados_antes.to_excel(writer, sheet_name="Pendentes", index=False)
            buf_xlsx_single.seek(0)
            st.download_button(
                label="📗 Baixar Excel (uma aba)",
                data=buf_xlsx_single,
                file_name="dados_pendentes.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                use_container_width=True
            )
        except Exception as e:
            st.error(f"Erro ao gerar Excel único: {e}")

    # ===== Percentual por Prefixo =====
    st.markdown('<a name="percentual-prefixo"></a>', unsafe_allow_html=True)
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

        # --- Monta DF alinhado por Prefixo ---
        idx = sorted(totais.index.union(antes.index), key=lambda x: str(x))
        dfm = pd.DataFrame(index=idx)
        dfm["Total"] = totais.reindex(idx).fillna(0).astype(int)
        dfm["Pendentes"] = antes.reindex(idx).fillna(0).astype(int)
        dfm["%Pendentes"] = (dfm["Pendentes"] / dfm["Total"] * 100).replace([np.inf, -np.inf], 0).fillna(0)

        # --- Método de cálculo ---
        metodo = st.radio(
            "Como calcular a coluna **Faltam para 90%**?",
            ["Sempre para cima (ceil)", "Compensado (maior resto)"],
            horizontal=True
        )

        # Quantidade‑meta (90% do total, arredondando para cima por prefixo)
        dfm["Meta_90%_Qtd"] = np.ceil(meta_pct * dfm["Total"]).astype(int)

        # Base "faltam" por ceil (sempre não-negativo)
        dfm["Faltam_Ceil"] = (dfm["Meta_90%_Qtd"] - dfm["Pendentes"]).clip(lower=0).astype(int)

        if metodo == "Sempre para cima (ceil)":
            df_out = dfm[["Total", "Pendentes", "%Pendentes", "Meta_90%_Qtd", "Faltam_Ceil"]].rename(
                columns={"Faltam_Ceil": "Faltam para 90% (ceil)"}
            )
        else:
            # --- Compensado (método do maior resto / Hamilton) ---
            # Ideal "faltam" (pode ter fração) e zera negativos
            ideal = meta_pct * dfm["Total"] - dfm["Pendentes"]
            ideal_pos = ideal.clip(lower=0)

            base = np.floor(ideal_pos).astype(int)         # parte inteira
            resto = (ideal_pos - base)                     # fração 0..1

            # Total inteiro a alocar = arredondamento do total ideal
            total_target = int(round(ideal_pos.sum()))
            to_allocate = max(0, total_target - int(base.sum()))

            # Distribui +1 pelos maiores restos
            extra = pd.Series(0, index=dfm.index, dtype=int)
            if to_allocate > 0:
                # ordena por resto desc; em empate, mantém ordem estável
                ordem = resto.sort_values(ascending=False).index.tolist()
                for i, idx_pref in enumerate(ordem):
                    if i >= to_allocate:
                        break
                    extra.loc[idx_pref] += 1

            faltam_comp = (base + extra).astype(int)

            # Garante não-negativo
            faltam_comp = faltam_comp.clip(lower=0)

            df_out = dfm[["Total", "Pendentes", "%Pendentes"]].copy()
            df_out["Meta_90%_Qtd (compensado)"] = (df_out["Pendentes"] + faltam_comp).astype(int)
            df_out["Faltam para 90% (compensado)"] = faltam_comp.astype(int)

        st.markdown("## 🧪 Validação do cálculo (soma geral)")

        if metodo == "Sempre para cima (ceil)":
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

        # Formatação e exibição
        formatadores = {
            "%Pendentes": "{:.1f}%"
        }
        st.dataframe(
            df_out.style.format(formatadores),
            use_container_width=True
        )

        # Pequena legenda para explicar os métodos
        with st.expander("ℹ️ Entenda os métodos"):
            st.markdown(
                "- **Sempre para cima (ceil):** calcula `ceil(90%×Total) − Pendentes` por Prefixo (mínimo 0).\n"
                "- **Compensado (maior resto):** soma os ideais por Prefixo, usa a parte inteira e distribui os `+1` pelos **maiores restos**, "
                "reduzindo distorções em Prefixos muito pequenos."
            )
    st.info("""
**Observações**
- Entrada **somente CSV**.
""")