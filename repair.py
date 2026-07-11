import pikepdf
import sys
import shutil

path = 'C:/Users/Arnav/Downloads/Bookss/computer-networks-tanenbaum-5th-edition.pdf'
try:
    print('Reading with pikepdf...')
    # pikepdf relies on QPDF which can repair almost any broken PDF
    with pikepdf.open(path) as pdf:
        print('Writing repaired PDF...')
        pdf.save(path + '.repaired.pdf')
    
    # Replace the original with the repaired one
    shutil.move(path + '.repaired.pdf', path)
    print('Successfully repaired the PDF!')
except Exception as e:
    print('Error:', e)
