# Barra de Progresso + Cache para PDF — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Mostrar uma barra de progresso página-a-página durante o parsing de PDFs longos e fazer cache do resultado (via `st.session_state`) para que mudanças de filtro/slider não reprocessam o PDF.

**Architecture:** Alargar `parse_pdf` com um callback opcional `on_progress` que o `main.py` usa para atualizar uma `st.progress` por página. No `main.py`, detetar cache miss/hit comparando `hash(file_bytes)` com `st.session_state["last_pdf_hash"]`; no miss, mostrar a barra e chamar `parse_pdf` com callback; no hit, devolver os records guardados instantaneamente. Caminho Excel inalterado.

**Tech Stack:** Python 3, Streamlit (`st.progress`, `st.session_state`), pdfplumber, pandas.

**Spec de referência:** `docs/superpowers/specs/2026-06-18-progress-cache-pdf-design.md`

---

## File Structure

**Ficheiros modificados:**
- `parse_reservas.py` — alargar `parse_pdf(path)` para `parse_pdf(path, on_progress=None)`; chamar `on_progress` após cada página; suprimir stderr quando callback está definido; suportar abortar se callback devolver `False`.
- `main.py` — no ramo PDF, detetar cache miss/hit via `st.session_state` + `hash(file_bytes)`; no miss, criar `st.progress` e chamar `parse_pdf` com callback; no hit, devolver records do cache; limpar a barra no fim.

**Ficheiros criados:** Nenhum.

**Notas sobre testes:** O projeto não tem framework de testes. A verificação é manual/visual via Streamlit + snippets Python inline para confirmar o contrato do `on_progress`. Não se introduz framework de testes (fora de âmbito do spec).

---

### Task 1: Alargar `parse_pdf` com callback `on_progress`

**Files:**
- Modify: `parse_reservas.py:112-160` (função `parse_pdf`)

**Objetivo:** Permitir que um consumidor (o `main.py`) receba progresso página-a-página e possa abortar o parsing.

- [ ] **Step 1: Alterar a assinatura de `parse_pdf`**

Em `parse_reservas.py`, substituir:

```python
def parse_pdf(path):
    """Lê o PDF e devolve lista de dicionários (um por registo)."""
```

por:

```python
def parse_pdf(path, on_progress=None):
    """Lê o PDF e devolve lista de dicionários (um por registo).

    on_progress : callable opcional (pi, n_pages, n_records) -> bool|None.
        Chamado após cada página processada. Se devolver False, o parsing
        aborta e devolve os registos acumulados até ao momento.
        Quando None, o progresso vai para sys.stderr a cada 10 páginas
        (comportamento CLI).
    """
```

- [ ] **Step 2: Chamar `on_progress` e suportar abortar; suprimir stderr quando callback existe**

No interior do ciclo `for pi, page in enumerate(pdf.pages, 1):`, **depois** de `records.append(row)` (dentro do ciclo dos anchors) e **antes** do bloco `if pi % 10 == 0 or pi == n_pages:` que escreve para stderr, inserir a chamada ao callback e o check de abort. Substituir o bloco atual:

```python
                records.append(row)
            if pi % 10 == 0 or pi == n_pages:
                sys.stderr.write(f"  processadas {pi}/{n_pages} páginas"
                                 f" ({len(records)} registos)\n")
    return records
```

por:

```python
                records.append(row)
            # Feedback de progresso.
            if on_progress is not None:
                keep_going = on_progress(pi, n_pages, len(records))
                if keep_going is False:
                    break
            elif pi % 10 == 0 or pi == n_pages:
                sys.stderr.write(f"  processadas {pi}/{n_pages} páginas"
                                 f" ({len(records)} registos)\n")
    return records
```

Notas:
- O callback é chamado **uma vez por página**, após processar todos os anchors dessa página.
- `keep_going is False` (comparação explícita, não `not keep_going`) para que `None` (retorno omitido) não aborte.
- Quando `on_progress` está definido, o stderr por página é suprimido (evita duplicação). O callback é a única fonte de feedback.
- `break` sai do ciclo `for pi, page`; o `return records` devolve os registos acumulados (parciais se abortou, completos caso contrário).

- [ ] **Step 3: Verificar sintaxe**

```bash
python -c "import ast; ast.parse(open('parse_reservas.py', encoding='utf-8').read()); print('OK')"
```

Esperado: `OK`.

- [ ] **Step 4: Verificar o contrato do callback isoladamente (sem PDF)**

Confirmar que a assinatura está correta e que `on_progress=None` não quebra:

```bash
python -c "import parse_reservas as p; import inspect; sig=str(inspect.signature(p.parse_pdf)); print(sig)"
```

Esperado: `(path, on_progress=None)`.

- [ ] **Step 5: Verificar comportamento de abortar com um PDF simulado (se houver Reservas.pdf)**

Se `Reservas.pdf` existir na raiz, correr:

```bash
python -c "import parse_reservas as p; calls=[]; def cb(pi,n,r): calls.append((pi,n,r)); return pi>=3; recs=p.parse_pdf('Reservas.pdf', on_progress=cb); print('calls:', len(calls)); print('records:', len(recs))"
```

Esperado: `calls:` pequeno (3, ou o número de páginas até abortar) e `records:` > 0 (parciais). Se `Reservas.pdf` não existir, saltar e assinalar verificação pendente.

- [ ] **Step 6: Commit**

```bash
git add parse_reservas.py
git commit -m "feat: parse_pdf com callback on_progress por pagina (barra de progresso)"
```

---

### Task 2: Adicionar cache + barra de progresso no ramo PDF do `main.py`

**Files:**
- Modify: `main.py:75-103` (ramo `elif nome.endswith(".pdf"):`)

**Objetivo:** Detetar cache miss/hit via `st.session_state` + `hash(file_bytes)`; no miss, mostrar `st.progress` atualizada por `on_progress`; no hit, devolver records instantaneamente; limpar a barra no fim.

- [ ] **Step 1: Substituir o bloco do ramo PDF**

Em `main.py`, substituir o bloco atual do ramo PDF:

```python
    elif nome.endswith(".pdf"):
        import tempfile
        from pathlib import Path
        from parse_reservas import parse_pdf, to_dataframe
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                tmp.write(ficheiro.getvalue())
                tmp_path = Path(tmp.name)
            records = parse_pdf(tmp_path)
            if len(records) == 0:
                st.error("Não foi possível extrair registos do PDF. Verifique que o ficheiro é uma exportação válida da LISTAGEM DE RESERVAS.")
                st.stop()
            df = to_dataframe(records)
        except st.exceptions.StopException:
            raise
        except ImportError as e:
            missing = "pdfplumber" if "pdfplumber" in str(e) else ("pandas" if "pandas" in str(e) else str(e))
            st.error(f"Dependência em falta ({missing}). Instale com: pip install {missing}")
            st.stop()
        except Exception as e:
            st.error(f"Erro ao processar o PDF: {e}")
            st.stop()
        finally:
            if tmp_path is not None and tmp_path.exists():
                try:
                    tmp_path.unlink()
                except OSError:
                    pass
```

por:

```python
    elif nome.endswith(".pdf"):
        import tempfile
        from pathlib import Path
        from parse_reservas import parse_pdf, to_dataframe

        file_bytes = ficheiro.getvalue()
        file_hash = hash(file_bytes)

        # Cache por sessão: se já processámos este ficheiro, reutilizar.
        if (st.session_state.get("last_pdf_hash") == file_hash
                and st.session_state.get("last_pdf_records") is not None):
            records = st.session_state["last_pdf_records"]
        else:
            # Cache miss: mostrar barra de progresso e processar.
            progress_bar = st.progress(0, text="A iniciar processamento do PDF...")
            tmp_path = None
            try:
                with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
                    tmp.write(file_bytes)
                    tmp_path = Path(tmp.name)

                def on_progress(pi, n_pages, n_records):
                    progress_bar.progress(
                        pi / n_pages if n_pages else 1.0,
                        text=f"Página {pi}/{n_pages} ({n_records} registos)",
                    )
                    return True

                records = parse_pdf(tmp_path, on_progress=on_progress)
                if len(records) == 0:
                    st.error("Não foi possível extrair registos do PDF. Verifique que o ficheiro é uma exportação válida da LISTAGEM DE RESERVAS.")
                    st.stop()
                # Gravar no cache só em sucesso (records não vazios).
                st.session_state["last_pdf_hash"] = file_hash
                st.session_state["last_pdf_records"] = records
            except st.exceptions.StopException:
                raise
            except ImportError as e:
                missing = "pdfplumber" if "pdfplumber" in str(e) else ("pandas" if "pandas" in str(e) else str(e))
                st.error(f"Dependência em falta ({missing}). Instale com: pip install {missing}")
                st.stop()
            except Exception as e:
                st.error(f"Erro ao processar o PDF: {e}")
                st.stop()
            finally:
                if tmp_path is not None and tmp_path.exists():
                    try:
                        tmp_path.unlink()
                    except OSError:
                        pass
                progress_bar.empty()
        df = to_dataframe(records)
```

Notas:
- `file_hash = hash(file_bytes)` é determinístico dentro de uma sessão Python (suficiente para Streamlit, que vive numa sessão).
- No cache hit, `records` vem do `st.session_state` e o `df = to_dataframe(records)` corre sempre (rápido; não precisa de cache).
- O `progress_bar` é criado só no miss e limpo no `finally` (mesmo em erro).
- O cache só é gravado após confirmação de `len(records) > 0` (miss com records vazios não grava, para que o reran volte a tentar).
- `on_progress` devolve sempre `True` (não usamos abortar agora; YAGNI).
- A função `on_progress` é definida dentro do `try` para capturar `progress_bar` no closure.
- O `df = to_dataframe(records)` fica fora do `try/except` para correr tanto no hit como no miss (depois do `else`).

- [ ] **Step 2: Verificar sintaxe**

```bash
python -c "import ast; ast.parse(open('main.py', encoding='utf-8').read()); print('OK')"
```

Esperado: `OK`.

- [ ] **Step 3: Verificar import do main.py sem erro de runtime**

```bash
python -c "import main" 2>&1 | Select-Object -First 5
```

Esperado: apenas os warnings normais do Streamlit sobre ScriptRunContext (não erros).

- [ ] **Step 4: Verificação manual - cache miss (primeiro upload)**

Arrancar a app:

```bash
streamlit run main.py
```

Carregar um `Reservas.pdf`. Confirmar:
- Aparece uma barra de progresso que atualiza "Página X/Y (N registos)".
- Ao fim, a barra desaparece e a pivot aparece.
- Mudar o filtro "Faturada" → a pivot atualiza **instantaneamente**, sem barra de progresso (cache hit).
- Mudar o slider de meses → também instantâneo (cache hit).
- Carregar um PDF diferente → barra de progresso aparece outra vez (miss, hash diferente).

Se não houver `Reservas.pdf` de exemplo, saltar e assinalar verificação pendente.

- [ ] **Step 5: Commit**

```bash
git add main.py
git commit -m "feat: barra de progresso + cache (session_state) no ramo PDF"
```

---

### Task 3: Verificação final e code review

**Files:** Nenhum (verificação apenas).

- [ ] **Step 1: Confirmar commits**

```bash
git log --oneline -3
```

Esperado: ver os commits de Tasks 1-2 por cima do commit do spec.

- [ ] **Step 2: Confirmar working tree limpo**

```bash
git status
```

Esperado: `nothing to commit, working tree clean`.

- [ ] **Step 3: Confirmar CLI inalterado**

```bash
python -c "import parse_reservas as p; print(p.parse_pdf.__defaults__)"
```

Esperado: `(None,)` (o default de `on_progress`). Confirma que o CLI (`parse_pdf(path)` sem segundo arg) ainda funciona.

- [ ] **Step 4: Pedir code review (subagent)**

Dispatch do code reviewer subagent com:
- `DESCRIPTION`: Barra de progresso página-a-página via callback on_progress em parse_pdf; cache via st.session_state no ramo PDF do main.py (hash do ficheiro como chave).
- `PLAN_OR_REQUIREMENTS`: `docs/superpowers/specs/2026-06-18-progress-cache-pdf-design.md`
- `BASE_SHA`: commit anterior ao Task 1 (obter com `git rev-parse HEAD~2`)
- `HEAD_SHA`: `git rev-parse HEAD`

Agir sobre o feedback: corrigir Critical/Important antes de dar por concluído.

- [ ] **Step 5: Registar verificação manual pendente (se aplicável)**

Se o Step 4 da Task 2 foi saltado por falta de `Reservas.pdf`, registar essa pendência para o utilizador validar manualmente antes do merge/deploy.

---

## Self-Review do plano

**1. Spec coverage:**
- Objetivo 1 (barra de progresso): Task 1 (callback) + Task 2 (st.progress). ✓
- Objetivo 2 (cache): Task 2 (st.session_state + hash). ✓
- `parse_pdf` assinatura alargada: Task 1 Step 1. ✓
- `on_progress(pi, n_pages, n_records)`: Task 1 Step 2. ✓
- Abortar se `on_progress` devolve `False`: Task 1 Step 2 (`keep_going is False` → break). ✓
- `on_progress=None` mantém stderr: Task 1 Step 2 (`elif pi % 10...`). ✓
- Suprimir stderr quando callback existe: Task 1 Step 2 (ramo `if on_progress is not None` vs `elif`). ✓
- Cache via `st.session_state` (não `@st.cache_data`): Task 2 Step 1. ✓
- Chave = `hash(file_bytes)`: Task 2 Step 1. ✓
- Cache hit → instantâneo sem barra: Task 2 Step 1 (ramo `if`). ✓
- Cache miss → barra + callback: Task 2 Step 1 (ramo `else`). ✓
- Barra limpa no `finally`: Task 2 Step 1 (`progress_bar.empty()` no finally). ✓
- Cache gravado só em sucesso (records não vazios): Task 2 Step 1 (`if len(records) == 0: st.stop()` antes de gravar). ✓
- CLI inalterado: Task 1 Step 1 (default `on_progress=None`); Task 3 Step 3. ✓
- Excel inalterado: Task 2 só mexe no `elif pdf`. ✓
- Fora de âmbito respeitado: sem `@st.cache_data`, sem cancelamento, sem estimativa de tempo, sem cache Excel, sem persistência entre sessões. ✓

**2. Placeholder scan:** sem "TBD"/"TODO" nos passos; passos de verificação manual que dependem de `Reservas.pdf` estão explícitos sobre o comportamento quando falta (saltar + assinalar pendente). Aceitável.

**3. Type consistency:** `parse_pdf(path, on_progress=None)` definida em Task 1 e consumida em Task 2 com a mesma assinatura. `on_progress(pi, n_pages, n_records)` → `bool|None` em Task 1; em Task 2 o callback devolve `True` (compatível). `st.session_state["last_pdf_hash"]` e `["last_pdf_records"]` usados consistentemente entre hit e miss. `progress_bar` referenciado no `finally` é definido no início do `else` (escopo correto). ✓

Sem issues; plano pronto.