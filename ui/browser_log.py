"""Logs EXPLICATIVOS no console do navegador (DevTools → Console, tecla F12).

Princípio: o log é uma NARRATIVA em linguagem simples — cada passo diz o que o sistema
fez e POR QUÊ, com números traduzidos em significado ("custou menos de 1 centavo",
"0,8 s") em vez de jargão (BM25/RRF/tiers/tokens). Quem precisa do dado cru continua
tendo: o objeto técnico completo (retrieval_debug) vai anexado no FIM do grupo,
rotulado "detalhes técnicos".

Como: components.html injeta um <script> num iframe same-origin (st.markdown não executa
scripts) e escrevemos em window.parent.console — os grupos aparecem no console PRINCIPAL
da página. height=0: o iframe não ocupa espaço visual. O log só roda quando uma resposta
NOVA chega (não em re-render de histórico), então não há duplicatas.

Segurança: json.dumps + substituição de "</" impede que conteúdo do catálogo/resposta
feche o <script> e injete HTML (mesma postura anti-injeção do backend, aplicada aqui).
"""
from __future__ import annotations

import json

import streamlit.components.v1 as components

# Comportamento interno -> título amigável do grupo (mesma língua dos selos da UI).
_BEHAVIOR_TITLE = {
    "answer": "Resposta com fontes",
    "abstain": "Não consta no catálogo",
    "clarify": "Pedi mais contexto",
    "acknowledge_limitation": "Expliquei uma limitação do catálogo",
}


def _js(payload) -> str:
    """Serializa para dentro do <script> com segurança ("</" quebraria a tag script)."""
    return json.dumps(payload, ensure_ascii=False).replace("</", "<\\/")


def _seg(ms) -> str:
    """Milissegundos -> 'X,X s' (vírgula pt-BR). Tempo em segundos é o que humano entende."""
    try:
        return f"{float(ms) / 1000:.1f} s".replace(".", ",")
    except (TypeError, ValueError):
        return "?"


def _custo(usd) -> str:
    """Custo em linguagem de gente: a ordem de grandeza importa mais que a 6ª casa."""
    try:
        v = float(usd)
    except (TypeError, ValueError):
        return "?"
    if v == 0:
        return "custo zero"
    if v < 0.01:
        return f"menos de 1 centavo de dólar (US$ {v:.4f})".replace(".", ",")
    return f"US$ {v:.2f}".replace(".", ",")


def _explica_nota(n: str) -> str | None:
    """Traduz as notas técnicas do pipeline para narrativa simples. Nota desconhecida
    retorna None (vai como 'observação' crua — melhor cru que escondido)."""
    if "agregação determinística" in n:
        return ("o pedido era uma CONTA (mais antigo/mais recente) — o sistema calculou "
                "direto dos dados do catálogo; a IA não faz aritmética aqui")
    if n.startswith("agrupamento por categoria"):
        return ("organizei os livros por categoria via programação (contagem exata, "
                "não estimativa da IA) — " + n.split("(")[-1].rstrip(")"))
    if n.startswith("diversidade:"):
        return ("o pedido era de livros VARIADOS entre si — selecionei um por faixa de "
                "público disponível nos dados (" + n.split(":", 1)[1].strip() + ")")
    if "title_lookup: ausente" in n:
        return ("procurei o título exato no catálogo e ele NÃO EXISTE — respondi "
                '"não temos" sem nem acionar a IA (zero chance de inventar uma edição)')
    if "title_lookup: encontrado" in n:
        return "o título pedido EXISTE no catálogo — confirmei nos dados antes de responder"
    if n.startswith("filtro temático"):
        return ("o filtro de gênero zerou os resultados; afrouxei SÓ o gênero e mantive "
                "as restrições factuais (ano/idioma/público)")
    if "nenhum livro satisfaz" in n:
        return "nenhum livro atende aos filtros pedidos — preferi dizer isso a forçar uma resposta"
    if n.startswith("roteamento: tier="):
        tier = n.split("tier=")[1].split(" ")[0]
        modelo = n.split("-> ")[-1]
        extra = " | a chamada idêntica já existia em cache — saiu de graça" if "cache" in n else ""
        if tier == "light":
            return (f"a tarefa era SIMPLES (só narrar um fato já calculado), então usei a "
                    f"IA econômica ({modelo}) — ~4× mais barata, mesmo resultado{extra}")
        if tier == "heavy":
            return f"a tarefa era uma síntese LONGA, então usei a IA mais forte ({modelo}){extra}"
        return f"tarefa típica de busca e resumo — IA padrão ({modelo}){extra}"
    if n.startswith("geração degradada"):
        return ("a IA falhou neste passo — entreguei uma resposta básica montada "
                "diretamente dos dados (sem IA), em vez de deixar você sem nada")
    if "cache semântico" in n:
        return "uma pergunta quase idêntica já tinha sido respondida — reaproveitei a resposta"
    return None


def _fluxo(question: str, data: dict) -> list[str]:
    """Narra o caminho percorrido, passo a passo, em linguagem simples. Tudo defensivo
    (.get): o log nunca pode quebrar a resposta."""
    dbg = data.get("retrieval_debug") or {}
    notes = [n for n in (dbg.get("notes") or []) if isinstance(n, str)]
    lat = dbg.get("latency_ms") or {}
    passos: list[str] = []

    if dbg.get("from_cache"):
        passos.append("💾 Eu já tinha respondido essa pergunta (ou uma quase igual) — "
                      "reaproveitei a resposta pronta: instantânea e com custo zero.")
        return passos

    passos.append(f"📥 Recebi a pergunta e removi caracteres invisíveis/perigosos por segurança "
                  f"({len(question)} caracteres). Não havia resposta guardada — caminho completo.")

    fonte = (dbg.get("plan") or {}).get("source", "?")
    como = ("a IA mais leve interpretou o que você quer" if fonte == "llm"
            else "regras automáticas interpretaram o que você quer (sem custo de IA)")
    t = f" — levou {_seg(lat['planner_ms'])}" if "planner_ms" in lat else ""
    passos.append(f"🧭 Entendi a intenção: {como}{t}: identifiquei filtros (ano/gênero/público) "
                  f"e o TIPO do pedido (busca, conta, lista, checagem de título…).")

    cand = dbg.get("candidate_count")
    if cand is not None:
        passos.append(f"🔢 Apliquei os filtros objetivos no catálogo: dos 200 livros, "
                      f"{cand} atendem aos critérios factuais.")

    # Caminhos especiais (conta/agrupamento/título/relaxamento) — na ordem em que ocorreram
    for n in notes:
        exp = _explica_nota(n)
        if exp and not n.startswith("roteamento"):   # roteamento entra no passo da IA, abaixo
            passos.append(f"⚙️ {exp}.")

    if "retrieval_ms" in lat:
        n_ids = len(dbg.get("retrieved_ids") or [])
        passos.append(f"🔎 Busquei os mais parecidos com o pedido combinando significado e "
                      f"palavras exatas: selecionei os {n_ids} melhores em {_seg(lat['retrieval_ms'])}.")

    rot = next((n for n in notes if n.startswith("roteamento")), None)
    if "generation_ms" in lat:
        exp_rot = (_explica_nota(rot) + " — " ) if rot and _explica_nota(rot) else ""
        passos.append(f"✍️ {exp_rot}a IA escreveu a resposta usando SOMENTE os livros "
                      f"selecionados (proibida de usar conhecimento de fora), "
                      f"em {_seg(lat['generation_ms'])}.")

    refs = data.get("references") or []
    passos.append(f"✅ Conferi cada livro citado contra a lista do que foi realmente "
                  f"recuperado: {len(refs)} referência(s) confirmada(s) — citação inventada "
                  f"é descartada automaticamente.")

    passos.append(f"💰 Resumo: {_custo(dbg.get('estimated_cost_usd'))} · tempo total "
                  f"{_seg(lat.get('total_ms'))}.")
    return passos


def log_health(health: dict) -> None:
    """Loga UMA vez por sessão a conexão com o backend, em linguagem simples."""
    resumo = (f"{health.get('catalog_size', '?')} livros no catálogo · "
              f"busca inteligente {'ativa' if health.get('semantic_ready') else 'no modo básico (palavras-chave)'} · "
              f"IA {'conectada via ' + str(health.get('llm_backend', '?')) if health.get('llm_available') else 'DESLIGADA (modo degradado)'}"
              f" ({health.get('model', '?')})")
    script = f"""<script>
      const c = (window.parent && window.parent.console) || console;
      c.info('%c[curadoria]%c ' + {_js(resumo)}, 'color:#0f62fe;font-weight:bold', 'color:inherit');
      c.log('   detalhes técnicos da conexão:', {_js(health)});
    </script>"""
    components.html(script, height=0)


def log_qa(question: str, data: dict) -> None:
    """Loga o grupo completo de UMA pergunta/resposta: narrativa simples + livros usados,
    com os detalhes técnicos crus anexados no fim (para quem precisar auditar a fundo)."""
    dbg = data.get("retrieval_debug") or {}
    titulo = _BEHAVIOR_TITLE.get(str(dbg.get("behavior")), str(dbg.get("behavior")))
    payload = {
        "titulo": titulo,
        "pergunta": question,
        "passos": _fluxo(question, data),
        "resposta": data.get("answer"),
        "livros_usados": [f"{r.get('id')} · {r.get('titulo')} ({r.get('ano_publicacao')})"
                          for r in (data.get("references") or [])],
        "tecnico": dbg,
    }
    script = f"""<script>
      const p = {_js(payload)};
      const c = (window.parent && window.parent.console) || console;
      c.groupCollapsed('%c[curadoria]%c ' + p.titulo + ' — ' + p.pergunta,
                       'color:#0f62fe;font-weight:bold', 'color:inherit');
      c.log('O que aconteceu, passo a passo:');
      p.passos.forEach((s, i) => c.log('  ' + (i + 1) + '. ' + s));
      c.log('Resposta dada:', p.resposta);
      if (p.livros_usados.length) c.log('Livros usados como fonte:', p.livros_usados);
      else c.log('Livros usados como fonte: nenhum (abstenção ou nada relevante).');
      c.log('— detalhes técnicos completos (para a equipe):', p.tecnico);
      c.groupEnd();
    </script>"""
    components.html(script, height=0)
