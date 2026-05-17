"""Phase 2.1 — NMF topic-based keyword network."""
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Patch
import numpy as np
import networkx as nx
from sklearn.feature_extraction.text import TfidfVectorizer, ENGLISH_STOP_WORDS
from sklearn.decomposition import NMF
from _common import parse_and_load, get

ctx = parse_and_load()
rows, idx = ctx["rows"], ctx["idx"]
out_dir = ctx["base_dir"] / "2_content"; out_dir.mkdir(parents=True, exist_ok=True)

stop_words = list(ENGLISH_STOP_WORDS) + [
    "model", "based", "using", "used", "paper", "study", "research", "analysis",
    "approach", "results", "also", "can", "one", "two", "may", "proposed",
    "different", "new", "system", "systems", "china", "chinese", "steel", "iron",
    "carbon", "emission", "emissions", "industry"
]

texts = [f"{get(r, idx, 'title', '')} {get(r, idx, 'abstract', '')} {get(r, idx, 'author_keywords', '')}" for r in rows]

tfidf = TfidfVectorizer(max_features=2000, stop_words=stop_words, max_df=0.85, min_df=3, ngram_range=(1,2))
X = tfidf.fit_transform(texts)
terms = tfidf.get_feature_names_out()
n_topics = 6
nmf = NMF(n_components=n_topics, random_state=42, max_iter=500, init="nndsvd")
W = nmf.fit_transform(X); H = nmf.components_
dom = W.argmax(axis=1)
topic_colors = ["#2196F3", "#FF9800", "#4CAF50", "#9C27B0", "#F44336", "#00BCD4"]
TOP_N = 8
tt = {i: [terms[j] for j in H[i].argsort()[-TOP_N:][::-1]] for i in range(n_topics)}
tc = {i: [H[i, j] for j in H[i].argsort()[-TOP_N:][::-1]] for i in range(n_topics)}

G = nx.Graph()
paper_counts = np.bincount(dom, minlength=n_topics)
for i in range(n_topics):
    G.add_node(f"T{i+1}", node_type="topic", weight=int(paper_counts[i]), color=topic_colors[i])

primary, max_c = {}, {}
for i in range(n_topics):
    for term, coeff in zip(tt[i], tc[i]):
        if term not in max_c or coeff > max_c[term]:
            max_c[term] = coeff; primary[term] = i
for term, pi in primary.items():
    G.add_node(term, node_type="term", weight=max_c[term], color=topic_colors[pi])
for i in range(n_topics):
    for term, coeff in zip(tt[i], tc[i]):
        if coeff > 0: G.add_edge(f"T{i+1}", term, weight=coeff, edge_type="membership")
for i in range(n_topics):
    for j in range(i+1, n_topics):
        ov = int(np.sum((W[:, i] > 0.15) & (W[:, j] > 0.15)))
        if ov >= 2: G.add_edge(f"T{i+1}", f"T{j+1}", weight=ov, edge_type="overlap")

fig, (ax_left, ax) = plt.subplots(1, 2, figsize=(20, 11), gridspec_kw={"width_ratios": [1, 1.4]})

# Left bars
y_off = 0; yt, yl = [], []
for i in range(n_topics):
    tt_i, tc_i = tt[i][:5], tc[i][:5]
    yp = list(range(y_off, y_off + 5))
    ax_left.barh(yp, tc_i, color=topic_colors[i], alpha=0.85, edgecolor="white", height=0.7,
                 label=f"T{i+1}: {', '.join(tt_i[:3])}")
    for j, (term, coeff) in enumerate(zip(tt_i, tc_i)):
        yl.append(term); yt.append(y_off + j)
        ax_left.text(coeff + 0.003, y_off + j, f"{coeff:.3f}", va="center", fontsize=9, color="#37474F")
    y_off += 6
ax_left.set_yticks(yt); ax_left.set_yticklabels(yl, fontsize=10); ax_left.invert_yaxis()
ax_left.set_xlabel("NMF coefficient", fontsize=13)
ax_left.set_title("2.1 Top 5 terms per topic", fontsize=15, fontweight="bold")
ax_left.legend(fontsize=8, loc="lower right", framealpha=0.9)
ax_left.set_xlim(0, max(max(tc[i][:5]) for i in range(n_topics)) * 1.35)

# Right network
topic_nodes = [n for n, d in G.nodes(data=True) if d["node_type"] == "topic"]
term_nodes = [n for n, d in G.nodes(data=True) if d["node_type"] == "term"]
pos = {}
for k, node in enumerate(topic_nodes):
    a = 2*np.pi*k/len(topic_nodes) - np.pi/2
    pos[node] = np.array([2.5*np.cos(a), 2.5*np.sin(a)])
np.random.seed(42)
for term in term_nodes:
    p = primary.get(term, 0)
    base = pos[f"T{p+1}"]
    pos[term] = base*np.random.uniform(0.55, 1.6)/2.5 + np.random.uniform(-0.3, 0.3, 2)

for a, b, d in G.edges(data=True):
    w = d["weight"]
    if d.get("edge_type") == "membership":
        nx.draw_networkx_edges(G, pos, edgelist=[(a, b)], alpha=0.15, edge_color="#90A4AE",
                               width=w*8, ax=ax)
    else:
        nx.draw_networkx_edges(G, pos, edgelist=[(a, b)], alpha=0.4, edge_color="#37474F",
                               width=w*0.3, style="dashed", ax=ax)

nx.draw_networkx_nodes(G, pos, nodelist=topic_nodes,
                       node_size=[G.nodes[n]["weight"]*40 + 300 for n in topic_nodes],
                       node_color=[G.nodes[n]["color"] for n in topic_nodes],
                       alpha=0.9, edgecolors="white", linewidths=2, ax=ax)
nx.draw_networkx_nodes(G, pos, nodelist=term_nodes,
                       node_size=[G.nodes[n]["weight"]*300 + 40 for n in term_nodes],
                       node_color=[G.nodes[n]["color"] for n in term_nodes],
                       alpha=0.7, edgecolors="white", linewidths=0.5, ax=ax)
nx.draw_networkx_labels(G, {n: pos[n]*1.15 for n in topic_nodes},
                        labels={n: n for n in topic_nodes}, font_size=11, font_weight="bold", ax=ax)
nx.draw_networkx_labels(G, pos, labels={n: n for n in term_nodes}, font_size=9, ax=ax)

ax.legend(handles=[Patch(facecolor=topic_colors[i], label=f"T{i+1}: {', '.join(tt[i][:3])}")
                   for i in range(n_topics)],
          fontsize=9, loc="upper left", title="NMF Topics", title_fontsize=11)
ax.set_title("2.1 NMF Keyword Network", fontsize=15, fontweight="bold")
ax.axis("off"); ax.set_xlim(-3.5, 3.5); ax.set_ylim(-3.5, 3.5)

plt.suptitle(f"{ctx['sheet_name']}", fontsize=15, y=1.01)
plt.tight_layout()
fig.savefig(out_dir / "2.1_keyword_network.png", dpi=150, bbox_inches="tight")
plt.close()
print(f"[{ctx['sheet_name']}] saved {out_dir / '2.1_keyword_network.png'}")
