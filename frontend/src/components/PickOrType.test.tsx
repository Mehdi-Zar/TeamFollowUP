import { describe, it, expect } from "vitest";
import { useState, type ReactElement } from "react";
import { fireEvent, render, screen } from "@testing-library/react";
import { I18nProvider } from "../i18n";
import PickOrType from "./PickOrType";

/**
 * A pick from the list must stick.
 *
 * It did not: after reporting the pick, the component also emptied the text
 * (`onText("")`). The milestone form reads "text" as "the dependency is free
 * text", so picking a tribe or a squad was undone on the spot and the list fell
 * back to "none". The owner and theme fields lost their pick the same way.
 */
type Dep = { kind: "squad" | "tribe" | "text" | null; squad: number | null; tribe: number | null; text: string };

function DependencyField() {
  const [d, setD] = useState<Dep>({ kind: null, squad: null, tribe: null, text: "" });
  return (
    <>
      <PickOrType id="dep"
        groups={[
          { label: "Squad", options: [{ value: "s:1", label: "Squad A" }] },
          { label: "Tribe", options: [{ value: "t:7", label: "New tribe" }] },
        ]}
        picked={d.kind === "squad" && d.squad ? `s:${d.squad}` : d.kind === "tribe" && d.tribe ? `t:${d.tribe}` : null}
        text={d.kind === "text" ? d.text : ""}
        onPick={(v) => setD(v?.startsWith("s:") ? { kind: "squad", squad: Number(v.slice(2)), tribe: null, text: "" }
          : v?.startsWith("t:") ? { kind: "tribe", tribe: Number(v.slice(2)), squad: null, text: "" }
          : { kind: null, squad: null, tribe: null, text: "" })}
        onText={(txt) => setD({ kind: "text", squad: null, tribe: null, text: txt })} />
      <output data-testid="state">{JSON.stringify(d)}</output>
    </>
  );
}

function OwnerField() {
  const [owner, setOwner] = useState("");
  const names = ["Alice Martin", "Bob Durand"];
  return (
    <>
      <PickOrType id="owner" groups={[{ options: names.map((n) => ({ value: n, label: n })) }]}
        picked={names.includes(owner) ? owner : null} text={names.includes(owner) ? "" : owner}
        onPick={(v) => setOwner(v ?? "")} onText={setOwner} />
      <output data-testid="owner">{owner}</output>
    </>
  );
}

const wrap = (ui: ReactElement) => render(<I18nProvider>{ui}</I18nProvider>);

describe("PickOrType", () => {
  it("keeps a tribe picked as a dependency", () => {
    wrap(<DependencyField />);
    const select = document.getElementById("dep") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "t:7" } });
    expect(JSON.parse(screen.getByTestId("state").textContent!)).toMatchObject({ kind: "tribe", tribe: 7 });
    expect(select.value).toBe("t:7");
  });

  it("keeps a squad picked as a dependency", () => {
    wrap(<DependencyField />);
    const select = document.getElementById("dep") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "s:1" } });
    expect(select.value).toBe("s:1");
  });

  it("keeps an owner picked from the list", () => {
    wrap(<OwnerField />);
    const select = document.getElementById("owner") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "Bob Durand" } });
    expect(screen.getByTestId("owner").textContent).toBe("Bob Durand");
    expect(select.value).toBe("Bob Durand");
  });

  it("keeps the text field open when the typed text matches an item, to type on", () => {
    wrap(<OwnerField />);
    const select = document.getElementById("owner") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "__other__" } });
    let input = document.querySelector("input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "Bob Durand" } });
    input = document.querySelector("input") as HTMLInputElement;
    expect(input).not.toBeNull();
    expect(input.value).toBe("Bob Durand");
    fireEvent.change(input, { target: { value: "Bob Durand Jr" } });
    expect(screen.getByTestId("owner").textContent).toBe("Bob Durand Jr");
  });

  it("offers each value once", () => {
    wrap(<PickOrType id="dup" picked={null} onPick={() => {}}
      groups={[{ options: [{ value: "Ann", label: "Ann" }] }, { options: [{ value: "Ann", label: "Ann" }] }]} />);
    const values = Array.from((document.getElementById("dup") as HTMLSelectElement).options).map((o) => o.value);
    expect(values.filter((v) => v === "Ann")).toHaveLength(1);
  });

  it("still takes free text through Other", () => {
    wrap(<OwnerField />);
    const select = document.getElementById("owner") as HTMLSelectElement;
    fireEvent.change(select, { target: { value: "__other__" } });
    const input = document.querySelector("input") as HTMLInputElement;
    fireEvent.change(input, { target: { value: "External vendor" } });
    expect(screen.getByTestId("owner").textContent).toBe("External vendor");
  });
});
