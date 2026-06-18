# Suporte a PDF no upload das Reservas — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Permitir upload de PDF na app Streamlit, usando `parse_reservas.py` como módulo para converter PDF → DataFrame compatível com o pipeline existente.

**Architecture:** Adicionar um ramo PDF no `main.py` que deteta a extensão do ficheiro carregado, escreve-o num tempfile, chama `parse_pdf()` do `parse_reservas.py` (importado dentro do ramo para não obrigar a instalar `pdfplumber` quando se usa Excel), converte os registos para DataFrame via nova função `to_dataframe()` do parser, e segue o pipeline inalterado. Corrigir o cabeçalho `"Dt.Criação"` → `"Dt. Criação"` no parser para alinhar com o que o `main.py` já espera.

**Tech Stack:** Python 3, Streamlit, pandas, pdfplumber, tempfile, pathlib.

**Spec de referência:** `docs/superpowers/specs/2026-06-18-pdf-upload-design.md`

---

## File Structure

**Ficheiros modificados:**
- `parse_reservas.py` — corrigir `REQUESTED_HEADER` (linha 42) e adicionar função `to_dataframe()` no fim do módulo (antes de `main`).
- `main.py` — alterar `st.file_uploader` (linha 47) para aceitar `pdf`; adicionar ramo PDF que produz `df` e converge para o pipeline existente.
- `requirements.txt` — adicionar `pdfplumber==0.11.4`.

**Ficheiros criados:**
- Nenhum. Tudo em ficheiros existentes.

**Notas sobre testes:** O projeto não tem framework de testes nem testes existentes. A verificação é manual/visual via Streamlit. As tarefas abaixo incluem passos de verificação manual explícitos (correr o CLI do parser, inspeção de colunas via snippet Python inline) em vez de `pytest`. Não se introduz framework de testes neste trabalho — fora de âmbito do spec.

---

### Task 1: Corrigir cabeçalho `REQUESTED_HEADER` no parser

**Files:**
- Modify: `parse_reservas.py:42`

**Objetivo:** Alinhar o cabeçalho do CSV reduzido com o que o `main.py` espera (`"Dt. Criação"` com espaço).

- [ ] **Step 1: Aplicar a correção**

Em `parse_reservas.py`, substituir a linha 42:

```python
REQUESTED_HEADER = ["Dt.Criação", "CNP", "Produto", "Qtd. Res.", "Faturada"]
```

por:

```python
REQUESTED_HEADER = ["Dt. Criação", "CNP", "Produto", "Qtd. Res.", "Faturada"]
```

- [ ] **Step 2: Verificar que o CLI continua a funcionar e o cabeçalho está correto**

Correr (precisa de um `Reservas.pdf` de exemplo na raiz do projeto; se não existir, saltar este passo e assinalar verificação pendente):

```bash
python parse_reservas.py Reservas.pdf _tmp_reservas.csv
```

Depois inspecionar a primeira linha de `_tmp_reservas.csv` (por exemplo com `Get-Content _tmp_reservas.csv -TotalCount 1`) e confirmar que começa com `Dt. Criação;CNP;Produto;Qtd. Res.;Faturada`.

Limpar o ficheiro temporário: `Remove-Item _tmp_reservas.csv, _tmp_reservas_full.csv -ErrorAction SilentlyContinue`.

- [ ] **Step 3: Commit**

```bash
git add parse_reservas.py
git commit -m "fix: corrigir cabeçalho 'Dt. Criação' no CSV reduzido do parser"
```

---

### Task 2: Adicionar função `to_dataframe()` ao parser

**Files:**
- Modify: `parse_reservas.py` (acrescentar função antes de `def main`)

**Objetivo:** Expor uma função reutilizável que converte `records` (lista de dicts do `parse_pdf`) num `pandas.DataFrame` com as colunas `REQUESTED_HEADER`, pronta a ser consumida pelo `main.py`.

- [ ] **Step 1: Adicionar import do pandas no topo do módulo**

No bloco de imports do `parse_reservas.py` (depois de `from pathlib import Path` e antes de `import pdfplumber`), adicionar:

```python
import pandas as pd
```

- [ ] **Step 2: Adicionar a função `to_dataframe`**

Inserir antes de `def main(argv):` (linha 171 atual):

```python
def to_dataframe(records, fields=REQUESTED, header=REQUESTED_HEADER):
    """Converte registos do parse_pdf num pandas.DataFrame com colunas legíveis.

    fields : nomes internos das colunas a extrair (por defeito REQUESTED).
    header : nomes legíveis a atribuir (por defeito REQUESTED_HEADER).

    Devolve Dt. Criação como str (conversão para datetime fica a cargo do
    consumidor, como já acontece no main.py) e Qtd. Res. como numérico
    (NaN onde não for possível converter).
    """
    if len(records) == 0:
        return pd.DataFrame(columns=header)
    df = pd.DataFrame([{h: r.get(f, "") for f, h in zip(fields, header)} for r in records])
    if "Qtd. Res." in df.columns:
        df["Qtd. Res."] = pd.to_numeric(df["Qtd. Res."], errors="coerce")
    return df
```

- [ ] **Step 3: Verificar import + função isoladamente**

Correr um snippet inline para confirmar que o módulo carrega e a função existe:

```bash
python -c "import parse_reservas as p; print(hasattr(p, 'to_dataframe')); print(p.REQUESTED_HEADER)"
```

Esperado:
```
True
['Dt. Criação', 'CNP', 'Produto', 'Qtd. Res.', 'Faturada']
```

- [ ] **Step 4: Verificar comportamento com lista vazia**

```bash
python -c "import parse_reservas as p; df=p.to_dataframe([]); print(list(df.columns)); print(len(df))"
```

Esperado:
```
['Dt. Criação', 'CNP', 'Produto', 'Qtd. Res.', 'Faturada']
0
```

- [ ] **Step 5: Commit**

```bash
git add parse_reservas.py
git commit -m "feat: adicionar to_dataframe() ao parser para consumo programático"
```

---

### Task 3: Adicionar `pdfplumber` ao `requirements.txt`

**Files:**
- Modify: `requirements.txt` (acrescentar uma linha)

- [ ] **Step 1: Adicionar a dependência**

No fim do `requirements.txt`, acrescentar:

```
pdfplumber==0.11.4
```

- [ ] **Step 2: Verificar que a linha foi adicionada**

```bash
Get-Content requirements.txt | Select-String pdfplumber
```

Esperado: uma linha `pdfplumber==0.11.4`.

- [ ] **Step 3: (Opcional) Instalar localmente para verificação posterior**

```bash
python -m pip install pdfplumber==0.11.4
```

Se o ambiente já tem todas as deps, isto confirma que a versão é instalável.

- [ ] **Step 4: Commit**

```bash
git add requirements.txt
git commit -m "deps: adicionar pdfplumber para suporte a upload de PDF"
```

---

### Task 4: Adicionar ramo PDF no `main.py`

**Files:**
- Modify: `main.py:47` (file_uploader) e `main.py:69-72` (bloco de leitura do ficheiro)

**Objetivo:** Aceitar PDF no upload; quando o ficheiro é PDF, escrever para tempfile, chamar `parse_pdf` + `to_dataframe`, e produzir um `df` com as mesmas 5 colunas que o ramo Excel, antes de continuar o pipeline inalterado.

- [ ] **Step 1: Alterar o `file_uploader` para aceitar `pdf`**

Em `main.py:47`, substituir:

```python
ficheiro = st.file_uploader("Carregar o ficheiro de reservas", type=["xlsx","xls"])
```

por:

```python
ficheiro = st.file_uploader("Carregar o ficheiro de reservas", type=["xlsx","xls","pdf"])
```

- [ ] **Step 2: Substituir o bloco de leitura por um ramo que deteta a extensão**

Substituir as linhas 69-73 do `main.py`:

```python
# Processamento de dados
if ficheiro:
    df = pd.read_excel(ficheiro, skiprows=17)
    colunas_a_manter = ['Dt. Criação', 'CNP', 'Produto', 'Qtd. Res.', 'Faturada']
    df = df[colunas_a_manter]
    df['Dt. Criação'] = pd.to_datetime(df['Dt. Criação'])
```

por:

```python
# Processamento de dados
if ficheiro:
    colunas_a_manter = ['Dt. Criação', 'CNP', 'Produto', 'Qtd. Res.', 'Faturada']
    nome = ficheiro.name.lower()
    if nome.endswith((".xlsx", ".xls")):
        df = pd.read_excel(ficheiro, skiprows=17)
        df = df[colunas_a_manter]
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
        except Exception as e:
            st.error(f"Erro ao processar o PDF: {e}")
            st.stop()
        finally:
            if tmp_path is not None and tmp_path.exists():
                tmp_path.unlink()
    else:
        st.error("Tipo de ficheiro não suportado. Use .xlsx, .xls ou .pdf.")
        st.stop()
    df['Dt. Criação'] = pd.to_datetime(df['Dt. Criação'])
```

Notas:
- O `import` do `parse_reservas` e `pdfplumber` (transitivo) fica dentro do ramo PDF, para o ramo Excel continuar a funcionar mesmo se `pdfplumber` não estiver instalado.
- `st.exceptions.StopException` é re-levanto para não ser capturado pelo `except Exception`.
- A linha `df['Dt. Criação'] = pd.to_datetime(df['Dt. Criação'])` foi movida para depois do `if/elif/else`, pois aplica-se a ambos os ramos.
- `ficheiro.getvalue()` lê todo o conteúdo do `UploadedFile` para bytes; em alguns Streamlit versions `ficheiro.read()` também funciona — manter `getvalue()` que é estável para `UploadedFile`.

- [ ] **Step 3: Verificação estática (import do main.py sem erro de sintaxe)**

```bash
python -c "import ast; ast.parse(open('main.py', encoding='utf-8').read()); print('OK')"
```

Esperado: `OK`.

- [ ] **Step 4: Verificação regressão Excel (manual)**

Arrancar a app localmente:

```bash
streamlit run main.py
```

Carregar um ficheiro `.xlsx` de reservas existente e confirmar que a tabela pivot aparece como antes (com os mesmos filtros e cores). Se não houver `.xlsx` de teste disponível, saltar este passo e assinalar verificação pendente.

- [ ] **Step 5: Verificação PDF (manual)**

Com a app a correr, carregar um `Reservas.pdf` de exemplo. Confirmar:
- Não há erro `st.error`.
- A tabela pivot aparece com as colunas de meses e totais, idêntica em estrutura à do Excel equivalente (não precisa de ter valores iguais se os dados diferem, só estrutura).
- Os avisos do parser (campos CNP/Produto em falta) aparecem na consola onde o `streamlit run` corre, mas não quebram a app.

Se não houver `Reservas.pdf` de exemplo, saltar este passo e assinalar verificação pendente.

- [ ] **Step 6: Commit**

```bash
git add main.py
git commit -m "feat: suportar upload de PDF no main.py via parse_reservas"
```

---

### Task 5: Verificação final e review de código

**Files:**
- Nenhum (verificação apenas).

- [ ] **Step 1: Confirmar que todos os commits estão feitos**

```bash
git log --oneline -5
```

Esperado: ver os commits de Tasks 1-4 por cima do commit do spec.

- [ ] **Step 2: Confirmar que não há ficheiros modified por confirmar**

```bash
git status
```

Esperado: `nothing to commit, working tree clean` (a não ser que `parse_reservas.py` já estivesse untracked no início — nesse caso deve estar tracked agora após os commits).

- [ ] **Step 3: Confirmar dependências**

```bash
Get-Content requirements.txt | Select-String pdfplumber
python -c "import pdfplumber; print(pdfplumber.__version__)"
```

Esperado: `pdfplumber==0.11.4` na primeira, e a versão instalada na segunda.

- [ ] **Step 4: Pedir code review (subagent)**

Dispatch do code reviewer subagent com:
- `DESCRIPTION`: Suporte a upload de PDF no main.py; parser exposto como módulo via to_dataframe(); cabeçalho Dt. Criação corrigido; pdfplumber adicionado.
- `PLAN_OR_REQUIREMENTS`: `docs/superpowers/specs/2026-06-18-pdf-upload-design.md`
- `BASE_SHA`: commit anterior ao Task 1 (obter com `git rev-parse HEAD~4`)
- `HEAD_SHA`: `git rev-parse HEAD`

Agir sobre o feedback conforme o skill `requesting-code-review`: corrigir Critical/Important antes de dar por concluído.

- [ ] **Step 5: Marcar verificação manual pendente como realizada (se aplicável)**

Se os passos 4 e 5 da Task 4 foram saltados por falta de ficheiros de exemplo, registar essa pendência no relatório de review para o utilizador validar manualmente antes do merge/deploy.

---

## Self-Review do plano

**1. Spec coverage:**
- Objetivo (upload PDF): Task 4. ✓
- Correção cabeçalho: Task 1. ✓
- `to_dataframe()`: Task 2. ✓
- Import tardio para não quebrar Excel: Task 4 Step 2. ✓
- tempfile + limpeza: Task 4 Step 2 (`try/finally`). ✓
- Erros (PDF vazio, extensão não suportada): Task 4 Step 2. ✓
- `pdfplumber` no requirements: Task 3. ✓
- CLI inalterado: Task 1 não mexe na lógica de parsing, só no header; Tasks 2-4 não mexem no CLI. ✓
- Fora de âmbito respeitado: sem CSV direto, sem refactor, sem testes automatizados. ✓

**2. Placeholder scan:** sem "TBD"/"TODO" nos passos; os passos de verificação manual que dependem de ficheiros de exemplo estão explícitos sobre o comportamento quando faltam (saltar + assinalar pendente). Aceitável.

**3. Type consistency:** `to_dataframe(records, fields=REQUESTED, header=REQUESTED_HEADER)` definida em Task 2 e consumida em Task 4 com a mesma assinatura. `REQUESTED_HEADER` corrigido em Task 1 é usado por omissão em Task 2. `parse_pdf(tmp_path)` matches the signature `parse_pdf(path)` no parser. ✓

Sem issues; plano pronto.