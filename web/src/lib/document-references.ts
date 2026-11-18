type TextNode = { type: string; value?: string; url?: string; children?: TextNode[] };

export function documentReferences() {
  return (tree: TextNode) => {
    function walk(node: TextNode) {
      if (!node.children || ["link", "linkReference", "code", "inlineCode"].includes(node.type)) return;
      node.children = node.children.flatMap(child => {
        if (child.type !== "text" || !child.value) { walk(child); return [child]; }
        const result: TextNode[] = [];
        let offset = 0;
        const pattern = /\b(?:brief|edit|legacy|research|scripts)\/[^\s<>`"()[\]]+?\.(?:markdown|md|txt|json|csv|log|yaml|yml|toml)\b/gi;
        for (const match of child.value.matchAll(pattern)) {
          const index = match.index!;
          if (index > offset) result.push({ type: "text", value: child.value.slice(offset, index) });
          result.push({ type: "link", url: match[0], children: [{ type: "text", value: match[0] }] });
          offset = index + match[0].length;
        }
        if (offset < child.value.length) result.push({ type: "text", value: child.value.slice(offset) });
        return result;
      });
    }
    walk(tree);
  };
}
