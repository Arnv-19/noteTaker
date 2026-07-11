import fitz
doc = fitz.open()
page = doc.new_page()
rect = fitz.Rect(100, 100, 200, 200)
annot = page.add_highlight_annot(rect)
annot.update()
print(f"Annot type: {annot.type}")
print(f"Annot rect: {annot.rect}")
print(f"Annot colors: {annot.colors}")
print(f"Num annots: {len(list(page.annots()))}")
for a in page.annots():
    print(a.type[0])
    print(a.colors.get('stroke'))
