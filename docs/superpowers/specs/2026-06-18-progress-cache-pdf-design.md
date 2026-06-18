# Design: Barra de Progresso + Cache para Processamento de PDF

**Data:** 2026-06-18
**Estado:** Aprovado por design (pendente validação final do utilizador)

## 1. Objetivo

1. Mostrar feedback visual ao utilizador (barra `st.progress` por página) durante o
   processamento de PDFs longos (138+ páginas), evitando a sensação de que a app
   parou ou bloqueou.
2. Fazer cache do resultado do parsing na sessão para que mudanças de filtro
   (Faturada, slider de meses, período de análise) não reprocessam o PDF.

## 2. Contexto

- `main.py:84` chama `parse_pdf(tmp_path)` de forma síncrona sem feedback na UI.
  Para PDFs longos, o utilizador não tem qualquer indicação de progresso.
- `parse_reservas.py:157-159` já escreve progresso para `sys.stderr` a cada 10
  páginas, mas isso é invisível ao utilizador do Streamlit (vai para a consola
  do servidor).
- Streamlit reexecuta o script completo a cada interação com um widget
  (mudança de filtro, slider, etc.). Sem cache, `parse_pdf` corre de novo a
  cada interação, reprocessando as 138 páginas — o que explica a lentidão
  observada ao mudar o filtro "Faturada".

## 3. Arquitetura / Componentes

### 3.1 `parse_reservas.py` — função `parse_pdf`

- Assinatura alargada: `parse_pdf(path, on_progress=None)`.
- `on_progress` é um callable opcional `on_progress(pi, n_pages, n_records)`
  chamado após cada página processada, onde:
  - `pi` — índice da página atual (1-based).
  - `n_pages` — total de páginas do PDF.
  - `n_records` — número de registos acumulados até ao momento.
- Se `on_progress` devolver `False`, o parsing aborta e devolve os registos
  parciais acumulados até ao momento. (Capacidade futura; não usada agora.)
- Quando `on_progress is None` (CLI standalone), mantém o comportamento
  atual: progresso vai para `sys.stderr` a cada 10 páginas.
- Quando `on_progress` está definido, suprime o stderr por página para evitar
  duplicação (a UI já mostra o progresso); mantém o resumo final se útil.

### 3.2 `main.py` — ramo PDF com cache via `st.session_state`

Usa `st.session_state` como cache (não `@st.cache_data`) porque:
- Permite mostrar a barra de progresso no cache miss (chama `parse_pdf`
  diretamente com callback).
- No cache hit (mesmo ficheiro, filtro mudou), devolve os records guardados
  sem reprocessar.
- Mais simples que orquestrar `@st.cache_data` + deteção miss/hit.
- Limitação aceitável: o cache é por sessão (refrescar a página reprocessa).

**Fluxo do ramo PDF:**

1. `file_bytes = ficheiro.getvalue()`
2. `file_hash = hash(file_bytes)` (chave de cache).
3. Verificar `st.session_state.get("last_pdf_hash") == file_hash`:
   - **Cache hit** (mesmo ficheiro, mudou filtro/slider):
     - `records = st.session_state["last_pdf_records"]` (instantâneo, sem UI).
   - **Cache miss** (ficheiro novo ou primeira vez):
     - `progress_bar = st.progress(0, text="A iniciar processamento do PDF...")`
     - Escrever `file_bytes` para `tempfile.NamedTemporaryFile(suffix=".pdf",
       delete=False)`.
     - Definir callback `on_progress(pi, n_pages, n_records)` que atualiza:
       `progress_bar.progress(pi / n_pages, text=f"Página {pi}/{n_pages} ({n_records} registos)")`
     - `records = parse_pdf(tmp_path, on_progress=on_progress)`
     - Guardar no cache: `st.session_state["last_pdf_hash"] = file_hash`,
       `st.session_state["last_pdf_records"] = records`.
     - Limpar tempfile (no `finally`, como já existe).
     - `progress_bar.empty()` para limpar a UI.
4. Validar `len(records) == 0` → `st.error(...)` + `st.stop()` (como hoje).
5. `df = to_dataframe(records)` (como hoje).
6. Resto do pipeline inalterado.

### 3.3 Tratamento de erros (mantém o existente + adaptações)

- `st.exceptions.StopException` re-levanto (como hoje).
- `except ImportError as e` com mensagem precisa (como hoje).
- `except Exception as e` → `st.error(f"Erro ao processar o PDF: {e}")` +
  `st.stop()` (como hoje).
- `finally` limpa o tempfile com `try/except OSError` (como hoje).
- **Novo:** em caso de exceção durante cache miss, não gravar no
  `st.session_state` (para que o próximo rerun volte a tentar com barra).
  O `finally` continua a limpar o tempfile; a barra de progresso é limpa
  no `finally` também.

## 4. Fluxo de dados

```
Upload PDF (ou mudança de filtro/slider)
   → file_bytes = ficheiro.getvalue()
   → file_hash = hash(file_bytes)
   → session_state["last_pdf_hash"] == file_hash?
        SIM (hit)  → records = session_state["last_pdf_records"]
                     (instantâneo, sem barra)
        NÃO (miss) → progress_bar = st.progress(0)
                     → tempfile.pdf
                     → parse_pdf(tmp_path, on_progress=atualiza_barra)
                          │ por cada página:
                          │   processa (igual a hoje)
                          │   callback → progress_bar.progress(pi/n, "Página X/Y (N registos)")
                     → session_state["last_pdf_hash"] = file_hash
                     → session_state["last_pdf_records"] = records
                     → progress_bar.empty()
                     → limpa tempfile
   → to_dataframe(records) → df
   → df['Dt. Criação'] = pd.to_datetime(..., dayfirst=True)
   → pipeline inalterado (filtro Faturada, agrupamentos, pivot, styled_df)
```

## 5. Decisões de implementação

- **`st.session_state` em vez de `@st.cache_data`:** o `session_state` permite
  mostrar a barra de progresso no miss (chama `parse_pdf` com callback) e
  detetar miss/hit trivialmente via comparação de hash. O `@st.cache_data`
  não permite tocar UI de dentro da função cached, o que impediria a barra.
  Limitação: cache por sessão; refrescar a página reprocessa. Aceitável para
  o âmbito do pedido.
- **Chave de cache = `hash(file_bytes)`:** simples e suficiente. `hash()`
  em Python é determinístico dentro de uma sessão (pode variar entre runs
  devido a `PYTHONHASHSEED`, mas como vivemos numa sessão Streamlit, não
  importa). Se no futuro for necessário persistência entre sessões, usar
  `hashlib.sha256(file_bytes).hexdigest()`.
- **Frequência do callback:** uma chamada por página. Para 138 páginas, são
  138 atualizações da barra — overhead desprezável comparado com
  `extract_words` por página.
- **Abortar (`on_progress` devolve `False`):** capacidade futura; o main.py
  não usa este ramo agora (YAGNI).
- **CLI inalterado:** `on_progress=None` mantém o stderr como hoje.
- **Caminho Excel:** não tem efeito (instantâneo); sem barra de progresso
  e sem cache.

## 6. Tratamento de erros

- **PDF sem registos** (miss): barra mostra "Página X/Y" até ao fim;
  `len(records) == 0` → `st.error("Não foi possível extrair registos...")`
  + `st.stop()`. O `st.session_state` não é gravado (não há records úteis
  para cache; o reran volta a tentar).
- **Exceção durante parsing** (miss): `except Exception` mostra `st.error`;
  barra é limpa no `finally`; `st.session_state` não é gravado.
- **Cache hit mas records vazios:** não deveria acontecer (miss só grava se
  `len(records) > 0`). Defensivamente, no hit, se
  `len(st.session_state["last_pdf_records"]) == 0`, reprocessa como miss.

## 7. Testes / Verificação

Sem testes automatizados no projeto; verificação manual/visual:

1. **Regressão Excel:** upload de `.xlsx` → pivot aparece como antes; sem
   barra de progresso (caminho Excel não tem barra).
2. **PDF cache miss (primeiro upload):** barra de progresso aparece e
   atualiza página a página; ao fim, pivot aparece; barra desaparece.
3. **PDF cache hit (mudar filtro "Faturada"):** muda filtro → pivot
   atualiza instantaneamente, sem barra de progresso, sem reprocessar.
4. **PDF cache hit (mudar slider de meses):** muda slider → pivot
   atualiza instantaneamente.
5. **Upload de PDF diferente:** novo upload → barra de progresso aparece
   (miss, hash diferente); pivot do novo ficheiro aparece.
6. **CLI inalterado:** `python parse_reservas.py Reservas.pdf out.csv`
   continua a mostrar progresso no stderr a cada 10 páginas.

## 8. Fora de âmbito

- `@st.cache_data` (em favor de `st.session_state` mais simples).
- Cancelamento pelo utilizador (botão "Parar") — requer arquitetura
  async/Thread, fora do pedido.
- Estimativa de tempo restante.
- Cache para o caminho Excel (instantâneo).
- Persistência do cache entre sessões (refrescar reprocessa).
- Cache de resultados do pipeline (agrupamentos/pivot) — só se faz cache
  do parsing; o resto do pipeline corre sempre (é rápido).