"""Logs estruturados no CONSOLE DO NAVEGADOR (DevTools → Console, tecla F12).

Por quê: quem avalia/testa a aplicação pela UI não deveria precisar do terminal do servidor
para auditar o que aconteceu. Cada resposta loga no navegador um grupo "[curadoria]" com:
- a PERGUNTA e o COMPORTAMENTO da resposta (answer/abstain/clarify/limitação);
- o FLUXO SEGUIDO passo a passo (planner→filtros→caminho determinístico→recuperação→
  tier do roteamento→geração→verificação de citações), com latência de cada etapa;
- as REFERÊNCIAS, custo real, tokens por chamada (com flag de cache) e o DEBUG BRUTO
  completo (retrieval_debug) para qualquer inspeção que o fluxo resumido não cubra.

Como: components.html injeta um <script> num iframe same-origin (st.markdown não executa
scripts) e escrevemos em window.parent.console — os grupos aparecem no console PRINCIPAL
da página. height=0: o iframe não ocupa espaço visual. O log só roda quando uma resposta
NOVA chega (não em re-render de histórico), então não há duplicatas no console.

Segurança: json.dumps + substituição de "</" impede que conteúdo do catálogo/resposta
feche o <script> e injete HTML (mesma postura anti-injeção do backend, aplicada aqui).
"""
from __future__ import annotations

import json

import streamlit.components.v1 as components


def _js(payload) -> str:
    """Serializa para dentro do <script> com segurança ("</" quebraria a tag script)."""
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def _flow(question: str, data: dict) -> list[str]:
    """Reconstrói o FLUXO percorrido pelo pipeline a partir do retrieval_debug — em ordem,
    com latências. Tudo defensivo (.get): log nunca pode quebrar a resposta."""
    dbg = data.get("retrieval_debug") or {}
    notes = dbg.get("notes") or []
    lat = dbg.get("latency_ms") or {}
    steps: list[str] = []

    if dbg.get("from_cache"):
        sem = next((n for n in notes if "cache semântico" in n), None)
        steps.append("CACHE de resposta: HIT "
                     + (f"({sem})" if sem else "(exato, sha256 da pergunta)")
                     + " → custo marginal US$ 0")
        return steps

    steps.append(f"pergunta sanitizada ({len(question)} chars) · caches de resposta: MISS")
    plan = dbg.get("plan") or {}
    steps.append("planner: fonte=" + str(plan.get("source", "?"))
                 + (f" · {lat['planner_ms']} ms" if "planner_ms" in lat else ""))
    steps.append(f"filtros duros de metadado: {dbg.get('candidate_count', '?')} candidatos")
    for n in notes:   # ramos determinísticos e avisos do retriever, na ordem em que ocorreram
        if any(k in n for k in ("agregação", "agrupamento", "diversidade", "title_lookup",
                                "relaxado", "vazia", "abstenção")):
            steps.append(f"caminho determinístico: {n}")
    if "retrieval_ms" in lat:
        tc = dbg.get("top_cosine")
        steps.append(f"recuperação híbrida (BM25+cosseno+RRF): {len(dbg.get('retrieved_ids') or [])} ids"
                     + (f" · top_cosine={round(tc, 3)}" if tc is not None else "")
                     + f" · {lat['retrieval_ms']} ms")
    rt = next((n for n in notes if n.startswith("roteamento")), None)
    if rt:
        steps.append(rt)   # tier light/standard/heavy + modelo (e cache de chamada, se hit)
    calls = (dbg.get("tokens") or {}).get("calls") or []
    if "generation_ms" in lat:
        gen = calls[-1] if calls else {}
        steps.append("geração ancorada (structured output): modelo=" + str(gen.get("model", "?"))
                     + (" · CACHE de chamada" if gen.get("cached") else "")
                     + f" · {lat['generation_ms']} ms")
    refs = data.get("references") or []
    ctx = dbg.get("context_ids") or []
    steps.append(f"verificação de citações: {len(refs)} referências validadas "
                 f"(gerador viu {len(ctx)} livros)")
    tok = dbg.get("tokens") or {}
    steps.append(f"TOTAL: US$ {dbg.get('estimated_cost_usd', 0)} · {lat.get('total_ms', '?')} ms"
                 f" · tokens {tok.get('input_tokens', 0)}/{tok.get('output_tokens', 0)} (in/out)")
    return steps


def log_health(health: dict) -> None:
    """Loga UMA vez por sessão o estado do backend (modo real: backend/modelo/semântica)."""
    script = f"""<script>
      const c = (window.parent && window.parent.console) || console;
      c.info('%c[curadoria]%c backend conectado', 'color:#0f62fe;font-weight:bold', 'color:inherit',
             {_js(health)});
    </script>"""
    components.html(script, height=0)


def log_qa(question: str, data: dict) -> None:
    """Loga o grupo completo de UMA pergunta/resposta (fluxo + referências + debug bruto)."""
    dbg = data.get("retrieval_debug") or {}
    payload = {
        "pergunta": question,
        "comportamento": dbg.get("behavior"),
        "fluxo": _flow(question, data),
        "resposta": data.get("answer"),
        "referencias": [{"id": r.get("id"), "titulo": r.get("titulo"),
                         "ano": r.get("ano_publicacao"), "score": r.get("score")}
                        for r in (data.get("references") or [])],
        "debug_bruto": dbg,
    }
    script = f"""<script>
      const p = {_js(payload)};
      const c = (window.parent && window.parent.console) || console;
      c.groupCollapsed('%c[curadoria]%c ' + p.comportamento + ' · ' + p.pergunta,
                       'color:#0f62fe;font-weight:bold', 'color:inherit');
      c.log('— fluxo seguido —');
      p.fluxo.forEach((s, i) => c.log('  ' + (i + 1) + '. ' + s));
      c.log('resposta:', p.resposta);
      c.log('referências:', p.referencias);
      c.log('debug bruto (retrieval_debug):', p.debug_bruto);
      c.groupEnd();
    </script>"""
    components.html(script, height=0)
