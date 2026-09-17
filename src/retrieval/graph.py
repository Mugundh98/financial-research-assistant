"""Knowledge graph over the corpus (networkx) — the 'lighter' retrieval item.

Nodes: companies, sectors, GAAP concepts, filings, documents.
Edges: company-in_sector->sector, company-reports->concept,
company-filed->filing, filing-has_section->document.

This enables relational lookups that flat retrieval can't answer directly, e.g.
"which companies report this concept?" or "what does this company disclose?".
"""
from __future__ import annotations

import networkx as nx


class KnowledgeGraph:
    def __init__(self):
        self.g = nx.MultiDiGraph()

    @classmethod
    def from_corpus(cls, corpus) -> "KnowledgeGraph":
        kg = cls()
        g = kg.g

        for co in corpus.companies:
            cn = f"company:{co.cik}"
            g.add_node(cn, kind="company", label=co.name, ticker=co.ticker, cik=co.cik)
            if co.sic_description:
                sn = f"sector:{co.sic_description}"
                if not g.has_node(sn):
                    g.add_node(sn, kind="sector", label=co.sic_description)
                g.add_edge(cn, sn, rel="in_sector")

        reported: set[tuple[str, str]] = set()
        for f in corpus.facts:
            cn = f"company:{f.cik}"
            kn = f"concept:{f.concept}"
            if not g.has_node(kn):
                g.add_node(kn, kind="concept", label=f.concept)
            if (cn, kn) not in reported and g.has_node(cn):
                g.add_edge(cn, kn, rel="reports")
                reported.add((cn, kn))

        for d in corpus.documents:
            cn = f"company:{d.cik}"
            fn = f"filing:{d.accession}"
            if not g.has_node(fn):
                g.add_node(fn, kind="filing", label=d.accession, form=d.form, filed=str(d.filed))
                if g.has_node(cn):
                    g.add_edge(cn, fn, rel="filed")
            dn = f"doc:{d.id}"
            g.add_node(dn, kind="document", label=d.section)
            g.add_edge(fn, dn, rel="has_section")

        return kg

    # ---- queries ---------------------------------------------------------- #
    def concepts_for(self, cik: str) -> list[str]:
        cn = f"company:{cik}"
        if not self.g.has_node(cn):
            return []
        return sorted(n.split(":", 1)[1] for n in self.g.successors(cn) if n.startswith("concept:"))

    def companies_for_concept(self, concept: str) -> list[str]:
        kn = f"concept:{concept}"
        if not self.g.has_node(kn):
            return []
        return sorted(p.split(":", 1)[1] for p in self.g.predecessors(kn) if p.startswith("company:"))

    def sector_peers(self, cik: str) -> list[str]:
        cn = f"company:{cik}"
        peers: set[str] = set()
        if not self.g.has_node(cn):
            return []
        for s in self.g.successors(cn):
            if s.startswith("sector:"):
                for p in self.g.predecessors(s):
                    if p.startswith("company:") and p != cn:
                        peers.add(p.split(":", 1)[1])
        return sorted(peers)

    def related_companies(self, cik: str, top: int = 5) -> list[tuple[str, int]]:
        """Companies ranked by number of co-reported GAAP concepts."""
        mine = set(self.concepts_for(cik))
        scores: dict[str, int] = {}
        for node, data in self.g.nodes(data=True):
            if data.get("kind") != "company" or node == f"company:{cik}":
                continue
            other_cik = data["cik"]
            shared = len(mine & set(self.concepts_for(other_cik)))
            if shared:
                scores[other_cik] = shared
        return sorted(scores.items(), key=lambda kv: -kv[1])[:top]

    def sections_for(self, cik: str) -> list[str]:
        cn = f"company:{cik}"
        if not self.g.has_node(cn):
            return []
        sections: list[str] = []
        for fn in self.g.successors(cn):
            if fn.startswith("filing:"):
                for dn in self.g.successors(fn):
                    if dn.startswith("doc:"):
                        sections.append(self.g.nodes[dn]["label"])
        return sections

    def stats(self) -> dict:
        by_kind: dict[str, int] = {}
        for _, data in self.g.nodes(data=True):
            kind = data.get("kind", "?")
            by_kind[kind] = by_kind.get(kind, 0) + 1
        return {
            "nodes": self.g.number_of_nodes(),
            "edges": self.g.number_of_edges(),
            "by_kind": by_kind,
        }
