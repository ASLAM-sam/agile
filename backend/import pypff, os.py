import pypff, os

os.makedirs(r'C:\Evidence\PDFs', exist_ok=True)

pst = pypff.file(); pst.open(r'"C:\Users\DELL\Downloads\r.danganan@salmangroup.com.001.pst"')

def folders(f):

    yield f

    for i in range(f.get_number_of_sub_folders()):

        yield from folders(f.get_sub_folder(i))

n = 0

for fol in folders(pst.get_root_folder()):

    for i in range(fol.get_number_of_sub_messages()):

        m = fol.get_sub_message(i); n += 1

        for j in range(m.get_number_of_attachments()):

            a = m.get_attachment(j)

            d = a.read_buffer(a.get_size())

            if d[:4] != b'%PDF': continue

            open(rf'C:\Evidence\PDFs\{n:04d}_{j}.pdf','wb').write(d)

print('done')