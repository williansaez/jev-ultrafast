<img src="docs/banner.svg" alt="Jev Ultrafast · Browser Use × TypeSafe" width="100%" />

# Jev Ultrafast ⚡

> [!IMPORTANT]
> **The Browser Use Cloud waitlist is open.** Get early access to ultrafast browser agents in the cloud.
> **[Join the waitlist →](https://browser-use.com/ultrafast?utm_source=github&utm_medium=readme&utm_campaign=jev-ultrafast)**

> [!NOTE]
> **Este é um fork pessoal** de [browser-use/jev-ultrafast](https://github.com/browser-use/jev-ultrafast). Ele acrescenta um servidor MCP e o suporte a um modelo de texto local via Ollama. Detalhes em [Este fork](#este-fork-servidor-mcp-e-ollama). O resto do README é o original.

**A browser agent with a dynamic, indexed action space.**

Give it one goal. [TypeSafe's Jev](https://docs.typesafe.ai/introduction) picks an operation and an element. A small LLM writes text only when the operation is `TYPE_TEXT`.

**Zürich → London on Google Flights in 7.1 seconds.** One natural-language goal, actual text generation, and loading waits included.

<a href="docs/demo.mp4"><img src="docs/demo.gif" alt="A real Google Flights search at 1× speed, with generated city names and dynamic operation/target decisions" width="100%" /></a>

[Watch the MP4](docs/demo.mp4) · [Measurements](docs/performance.md) · [Read the loop](jev_ultrafast/agent.py)

## Este fork: servidor MCP e Ollama

Três mudanças em relação ao [original](https://github.com/browser-use/jev-ultrafast). O loop do agente (`agent.py`, `browser.py`, `snapshot.js`, `questions.py`) está igual.

1. **Servidor MCP.** O agente vira uma tool que o Claude Code, o Claude Desktop ou qualquer cliente MCP podem chamar.
2. **Modelo de texto local.** O texto dos campos pode vir de um modelo no Ollama, sem custo e sem mandar o texto da página para a cloud.
3. **Browser dedicado.** O servidor arranca sozinho um Edge/Chromium com CDP quando ele não está a correr.

### O que muda em relação ao original

| Ficheiro | Mudança |
|---|---|
| `jev_ultrafast/mcp_server.py` (novo) | Servidor MCP (stdio) com as tools `jev_ultrafast_run` e `jev_ultrafast_doctor`. Arranca um browser dedicado quando a porta CDP não responde. Erros voltam como JSON com uma dica, em vez de derrubar o servidor. |
| `jev_ultrafast/model.py` | Nova opção `TEXT_MODEL_REASONING=effort_none`, que envia `reasoning_effort: "none"`, o formato que o endpoint `/v1` do Ollama respeita. As opções originais continuam iguais. |
| `pyproject.toml` | Dependência `mcp>=2.2.0` e comando `jev-ultrafast-mcp`. |
| `README.md` | Esta secção. |

O `.env.example` não mudou: continua a sugerir o OpenRouter. A configuração com Ollama está [abaixo](#configuração-env).

### Dois modelos, dois papéis

| Papel | Modelo | Configurável? |
|---|---|---|
| **Decisão**: qual operação (`CLICK`, `TYPE_TEXT`, `SELECT`, …) e qual elemento | Jev, sempre em `api.typesafe.ai` | Não. Exige `TYPESAFE_API_KEY`. |
| **Texto**: o valor a escrever num campo, só em `TYPE_TEXT` | Qualquer API compatível com OpenAI | Sim: `TEXT_MODEL_BASE_URL`, `TEXT_MODEL`, `TEXT_MODEL_API_KEY`. |

Clicar, navegar e escolher opções funciona sem modelo de texto. Ele só é chamado para preencher campos (caixa de pesquisa, formulário).

### Como o preenchimento de campos funciona (igual ao original)

1. O Jev escolhe `TYPE_TEXT` num campo.
2. O agente monta um contexto: objetivo, rótulo do campo, título e texto da página (até 6000 caracteres) e as últimas 6 ações.
3. Envia para `<TEXT_MODEL_BASE_URL>/chat/completions` e pede um JSON `{"text": "..."}`.
4. Valida (texto não vazio, até 2000 caracteres) e escreve no campo. Resposta inválida: não escreve nada e dá erro.
5. Sem `TEXT_MODEL_API_KEY` falha logo. Nenhum texto é fixo nem adivinhado.

### Modelo de texto: original vs este fork

| | Original | Este fork |
|---|---|---|
| Default no código | DeepSeek `deepseek-chat` | igual |
| Sugerido | OpenRouter `inception/mercury-2.5` (`.env.example`) | Ollama local `qwen3.5:9b` (este README) |
| Custo | pago | grátis |
| Texto da página | vai para a cloud | fica na máquina (só a decisão vai para a TypeSafe) |
| Latência | rápida | ~13 s no primeiro pedido (carga do modelo), depois rápida |

Valores de `TEXT_MODEL_REASONING`:

| Valor | Campo enviado | Para quem |
|---|---|---|
| (vazio) | `thinking: disabled` no DeepSeek, `reasoning.effort: low` nos outros | original |
| `none` | `reasoning.enabled: false` | original, formato OpenRouter |
| `effort_none` | `reasoning_effort: "none"` | **novo**, formato OpenAI, respeitado pelo Ollama |

Sem `effort_none`, o qwen3.5 no Ollama ignora o pedido de desligar o raciocínio, gasta ~320 tokens a pensar e devolve uma resposta vazia. Com ele, responde em ~7 tokens.

### Configuração (`.env`)

```bash
TYPESAFE_API_KEY=...                         # obrigatório
TYPESAFE_MODEL=jev-latest

# Texto via Ollama local
TEXT_MODEL_API_KEY=ollama                    # qualquer valor não vazio
TEXT_MODEL_BASE_URL=http://127.0.0.1:11434/v1
TEXT_MODEL=qwen3.5:9b
TEXT_MODEL_REASONING=effort_none

# Browser dedicado com CDP
BU_CDP_URL=http://127.0.0.1:9222
# JEV_EDGE_PROFILE_DIR=~/.config/browser-harness/edge-profile
# JEV_BROWSER_APP="Microsoft Edge"
```

O `.env` está no `.gitignore`. Não o commites.

### Browser

O Chromium 136+ ignora `--remote-debugging-port` no perfil por omissão. Por isso o servidor usa uma **segunda instância** do browser com perfil próprio. Quando `BU_CDP_URL` está definido e não responde, `jev_ultrafast_run` corre o equivalente a:

```bash
open -na "Microsoft Edge" --args --user-data-dir="$HOME/.config/browser-harness/edge-profile" --remote-debugging-port=9222 --no-first-run --no-default-browser-check
```

e espera até 20 s pela porta CDP. `JEV_BROWSER_APP` troca o browser (ex.: `"Google Chrome"`), `JEV_EDGE_PROFILE_DIR` troca o perfil. O arranque automático usa `open`, por isso só funciona no macOS. Noutros sistemas, arranca o browser à mão com as mesmas flags.

O browser normal do utilizador fica intocado. Depois de mudar variáveis de ambiente, corre `browser-harness --reload`, senão o daemon antigo continua com o ambiente velho.

### Registar o servidor MCP

Claude Code:

```bash
claude mcp add --scope user jev-ultrafast -- uv run --directory /caminho/jev-ultrafast --env-file /caminho/jev-ultrafast/.env jev-ultrafast-mcp
```

Claude Desktop / Cowork (`claude_desktop_config.json`):

```json
"jev-ultrafast": {
  "command": "uv",
  "args": ["run", "--directory", "/caminho/jev-ultrafast", "--env-file", "/caminho/jev-ultrafast/.env", "jev-ultrafast-mcp"]
}
```

### Tools

**`jev_ultrafast_run(url, goal, include_page_text=true, record_dir=null)`** corre um objetivo até ao fim (máximo de 60 ações, como no original).

- `goal`: um objetivo estreito com condição de paragem visível, 5 a 2000 caracteres. Sem seletores, listas de passos nem credenciais.
- `record_dir`: pasta opcional para screenshots JPEG por passo (mais lento).
- Devolve JSON com `status` (`done` ou `blocked`), `final_url`, `steps`, `elapsed_ms`, `history` (operação, ação, texto escrito, latência por passo), `note` e `page_text` (primeiros 4000 caracteres do texto visível).
- `status: done` é a palavra do agente. Confirma pelo `final_url` e pelo `page_text`.
- Em erro devolve `{"error": ..., "hint": ...}`. A chave em falta aparece aqui, não no arranque do servidor.

**`jev_ultrafast_doctor()`** verifica:

| Verificação | O que confirma |
|---|---|
| `typesafe_key` | `TYPESAFE_API_KEY` definido |
| `text_endpoint` | `<TEXT_MODEL_BASE_URL>/models` responde e lista o `TEXT_MODEL` |
| `cdp_browser` | o browser responde em `BU_CDP_URL` |
| `browser_harness` | resultado de `browser-harness doctor --json` |

Corre-o primeiro quando o `run` der erro.

Limites herdados do MVP: sem shadow DOM, iframes, canvas, uploads nem pop-ups. Use para pesquisar, abrir, filtrar e preencher formulários simples, não para logins ou pagamentos.

### Sincronizar com o original

```bash
git fetch upstream
git merge upstream/main
```

## The action space

Every observation produces a new element table:

```text
[1] button    Change ticket type · Round trip
[2] combobox  Where from?        · San Francisco
[3] combobox  Where to?          · empty
[4] textbox   Departure          · empty
...
```

The operations are `CLICK`, `TYPE_TEXT`, `SELECT`, `SCROLL_UP`, `SCROLL_DOWN`, `WAIT`, `DONE`, and `BLOCKED`. Only supported operations and targets are offered.

```text
                      one TypeSafe request
                     ┌───────────────────────────┐
page → element table → operation                 │
                     │ click_target              │
                     │ type_text_target          │
                     │ select_target, if present │
                     └─────────────┬─────────────┘
                         use the matching target
                                   │
                    CLICK [7] ─────┤──→ browser
                TYPE_TEXT [3] ─────┘
                          ↓
                   small LLM → text → browser
```

Target questions are speculative. If the operation is `CLICK`, only `click_target` can execute. Two decisions, **one network round trip**. Each target head contains only compatible elements. Native dropdown choices carry an observed element/option index.

There are no site-specific action scripts or prepared field strings in the policy. The Flights example supplies a goal and independently verifies the outcome. The screenshot renderer adds labels afterward; it does not drive the browser.

## Try it

```bash
git clone https://github.com/browser-use/jev-ultrafast.git
cd jev-ultrafast
uv sync
cp .env.example .env
# Add TYPESAFE_API_KEY and TEXT_MODEL_API_KEY.
uv run jev
```

Open **http://127.0.0.1:8766** and click **Start demo → Run automatically**. The inspector shows numbered elements, operation probabilities, target probabilities, and executed actions. **Choose next** pauses before execution.

Chrome connects through [Browser Harness](https://github.com/browser-use/browser-harness), installed by `uv sync`. Run `uv run browser-harness --doctor` if it needs connecting. Allow remote debugging in Chrome when prompted.

`TEXT_MODEL_API_KEY` is an OpenRouter key in the example configuration. The current demo uses `inception/mercury-2.5` with reasoning disabled. Gemini, GLM, and DeepSeek can also use the OpenAI-compatible text helper; configure the appropriate model, endpoint, and reasoning setting.

## Use the library

```python
from jev_ultrafast import Agent

with Agent(
    "https://www.google.com/travel/flights?hl=en",
    "Find one-way flights from Zurich to London on September 20, 2026, "
    "for one adult in economy. Stop when matching flight options are visible.",
) as agent:
    for state in agent.run():
        print(state["elapsed_ms"], state["status"])
```

Run with `uv run --env-file .env python your_script.py`. The same policy can run a different task:

```bash
uv run --env-file .env python examples/run.py \
  --url https://en.wikipedia.org/wiki/Main_Page \
  --goal 'Find and open the Wikipedia article about Gödel’s incompleteness theorems.'
```

`uv run --env-file .env python examples/flights.py --keep-open` performs the flight search, checks the actual route/date/results, and saves its trace. It does not select or book a flight.

## Why it moves

- **One request per decision cycle.** Operation and target heads share the same observed state.
- **No screenshots in the default agent loop.** Jev consumes structured state. The inspector opts into screenshots; the video uses a separate continuous screencast.
- **One browser call per snapshot.** Read visible controls, their names, values, and text atomically. Keep references to the actual DOM nodes.
- **Validate the selected target.** Clicks check the document, form values, target, and nearby context. Animation alone does not force another prediction. Resolve current geometry and reject covered controls before input.
- **Wait for useful state.** After typing into a combobox, wait for visible suggestions, capped at 200 ms. Other interactions get at most two animation frames or 50 ms. These reads happen after execution is logged.
- **Keep hidden tabs rendering.** Focus emulation prevents background animation throttling without switching Chrome's visible tab.
- **Send visible text.** Offscreen article bodies and footers do not fill the model context.
- **Reuse an interrupted text request.** A generated value survives a stale-page retry only if the entire text-helper input is unchanged.

Every executed target is resolved from an observed node. The executor rechecks page freshness and click occlusion. Model output never becomes selectors, coordinates, shell commands, or executable JavaScript. Text-helper output must parse as a small JSON object before typing.

## Small enough to read

| File | Job |
| --- | --- |
| [agent.py](jev_ultrafast/agent.py) | The complete loop and text-helper handoff |
| [snapshot.js](jev_ultrafast/snapshot.js) | Atomic DOM snapshot, indexed controls, freshness guards |
| [browser.py](jev_ultrafast/browser.py) | Browser connection, current geometry, execution |
| [model.py](jev_ultrafast/model.py) | Dynamic operation/target heads and text generation |
| [questions.py](jev_ultrafast/questions.py) | Model instructions |
| [demo.py](jev_ultrafast/demo.py) | Local inspector |

## Evidence and limits

The current video is a **7,073 ms** Google Flights run. Timing starts after initial page observation and includes model calls, generated text, browser work, stale decisions, and loading waits. A fresh independent check verifies the one-way setting, Zürich, London, September 20, 2026, and visible flight options. The video plays at 1×, with no opening hold and a 0.5-second final hold.

In six alternating runs with identical models and settings, both versions passed **3/3**. Median task time went from **9.450 s → 7.092 s**, a **25% reduction**; median browser protocol calls went from **1,092 → 101**. This is three repeats of one task on one browser profile, not a general reliability benchmark.

The same policy opened the requested Wikipedia article in **2.798 s** and passed a local hotel search/filter task in **1.896 s**. Runs, failures, source hashes, and measurement boundaries are in [performance.md](docs/performance.md).

A `DONE` choice still requires independent outcome verification. The DOM reader handles common HTML and ARIA controls, not the full accessible-name specification. Shadow roots, frames, canvas, uploads, pop-up tabs, nested scrolling, and arbitrary keyboard widgets remain outside this MVP. Owned tabs share the existing Chrome profile.

## Development

```bash
uv run ruff check .
uv run pytest
node --check jev_ultrafast/static/app.js
node --check jev_ultrafast/snapshot.js
uv build
```

Tests are offline. `uv run python scripts/check_guards.py` checks real controls in a local browser without model calls. Live examples and recording scripts make paid API calls. `scripts/record_flights.py <new-folder>` captures original browser timestamps; `scripts/render_demo.py <recording-folder>` renders that verified run at 1× and crops out the Google account strip. Credentials and raw traces stay ignored.

---

[Browser Use](https://github.com/browser-use/browser-use) · [Browser Harness](https://github.com/browser-use/browser-harness) · [TypeSafe speculative fan-out](https://docs.typesafe.ai/patterns/fan-out)
