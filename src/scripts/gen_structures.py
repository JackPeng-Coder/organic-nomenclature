# -*- coding: utf-8 -*-
import json
import re
import sys
from pathlib import Path

from rdkit import Chem
from rdkit.Chem import rdDepictor, rdMolDescriptors
from rdkit.Chem.Draw import rdMolDraw2D

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "src" / "data"))
from compounds import COMPOUNDS  # noqa: E402

OUT = ROOT / "src" / "assets" / "structures"
OUT.mkdir(parents=True, exist_ok=True)

INDEX = []
ERRORS = []


def draw_one(c):
    mol = Chem.MolFromSmiles(c["smiles"])
    if mol is None:
        raise ValueError("SMILES 无法解析")
    formula = rdMolDescriptors.CalcMolFormula(mol)

    rdDepictor.SetPreferCoordGen(True)
    rdDepictor.Compute2DCoords(mol)
    mol = rdMolDraw2D.PrepareMolForDrawing(mol, kekulize=True)

    if c.get("notes"):
        for atom in mol.GetAtoms():
            if atom.HasProp("molAtomMapNumber"):
                # Replace the element symbol with the locant: avoids "C:3" clutter.
                atom.SetProp("atomLabel", atom.GetProp("molAtomMapNumber"))
            else:
                atom.SetProp("atomLabel", str(atom.GetIdx() + 1))

    highlight_atoms = []
    if c.get("highlight") and not c.get("notes"):
        wanted = {int(x) for x in c["highlight"]}
        highlight_atoms = [
            a.GetIdx() for a in mol.GetAtoms()
            if a.HasProp("molAtomMapNumber") and int(a.GetProp("molAtomMapNumber")) in wanted
        ]

    d = rdMolDraw2D.MolDraw2DSVG(c.get("w", 720), c.get("h", 420))
    o = d.drawOptions()
    o.bondLineWidth = 2.4
    if c.get("notes"):
        o.minFontSize = 14
        o.maxFontSize = 18
    else:
        o.minFontSize = 17
        o.maxFontSize = 23
    o.annotationFontScale = 0.78
    o.useBWAtomPalette()
    o.clearBackground = True
    o.backgroundColour = (1.0, 1.0, 1.0, 1.0)
    o.padding = 0.07
    o.explicitMethyl = bool(c.get("explicit_methyl"))
    o.additionalAtomLabelPadding = 0.08

    kwargs = {}
    if highlight_atoms:
        hs = set(highlight_atoms)
        highlight_bonds = [
            b.GetIdx() for b in mol.GetBonds()
            if b.GetBeginAtomIdx() in hs and b.GetEndAtomIdx() in hs
        ]
        kwargs["highlightAtoms"] = []
        kwargs["highlightBonds"] = highlight_bonds
        kwargs["highlightBondColors"] = {i: (0.82, 0.48, 0.14) for i in highlight_bonds}

    d.DrawMolecule(mol, **kwargs)
    d.FinishDrawing()
    svg = d.GetDrawingText()
    svg = re.sub(r"<\?xml[^>]*\?>", "", svg)
    svg = re.sub(r"<!DOCTYPE[^>]*>", "", svg)
    svg = svg.replace("<svg ", '<svg preserveAspectRatio="xMidYMid meet" ', 1)
    path = OUT / f"{c['id']}.svg"
    path.write_text(svg, encoding="utf-8")

    INDEX.append({
        "id": c["id"],
        "name": c["name"],
        "smiles": c["smiles"],
        "formula": formula,
        "category": c.get("category", ""),
    })
    return formula, path


def main():
    for c in COMPOUNDS:
        try:
            formula, path = draw_one(c)
            print(f"OK  {c['id']:<32} {formula:<10} {path.name}")
        except Exception as e:
            ERRORS.append((c["id"], str(e)))
            print(f"ERR {c['id']:<32} {e}")

    (ROOT / "src" / "data" / "structures_index.json").write_text(
        json.dumps(INDEX, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(f"\n{len(INDEX)} structures generated; {len(ERRORS)} errors")
    if ERRORS:
        for cid, err in ERRORS:
            print("  ", cid, err)
        sys.exit(1)


if __name__ == "__main__":
    main()
