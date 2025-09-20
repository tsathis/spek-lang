"""Builds prompts for an external coding agent."""


class PromptGenerator:
    def __init__(self, spec):
        self.spec = spec

    def generation_prompt(self):
        p = [f"Implement {self.spec.sig.name}({', '.join(self.spec.sig.params)})"]
        p.append(f"Outcomes: {', '.join(self.spec.sig.outcomes)}")
        if self.spec.effects:
            p.append(f"Allowed effects: {', '.join(e.name for e in self.spec.effects)}")
        p.append("Examples:")
        for ex in self.spec.examples:
            p.append(f"  {ex.inputs} -> {ex.outcome}")
        return "\n".join(p)
