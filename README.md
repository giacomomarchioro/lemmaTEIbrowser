# lemmaTEIbrowser
A tool for creating databases of lemmas from a folder containing TEI files.

# Install

```
git clone https://github.com/giacomomarchioro/lemmaTEIbrowser
cd lemmaTEIbrowser
pip install -e .
```


# Import from TEI
First we have to download a dataset containing a folder with TEI files tagged:

```
git clone https://github.com/gpdsm/DiSMIdataset
```
Now we can use the command `lemma-import` to import the entries:

```
lemma-import ./DiSMIdataset/tei-xml
```
Missing word `xml:id` attributes are assigned automatically during import,
without changing the source XML files. Existing IDs are preserved, and the
same IDs are used in the database and generated HTML pages.

The import also generates the HTML pages used by the “Vedi nel testo” links
in `lemmaTEIbrowser/static/texts`. Failed files are reported with a nonzero
exit status; successfully imported files are preserved.
After the import is completed we use the command:

```
lemma-serve 
```
To run the application. The application will be available at http://127.0.0.1:5000.

# Database and file locations

`lemma-serve` searches the **SQLite database**, not the source XML files.
The XML folder is read only by `lemma-import`. Full-text links load the HTML
pages generated during import; templates, JavaScript and CSS come from the
installed `lemmaTEIbrowser` package.

Both commands use the same defaults, regardless of the terminal's directory:

| Resource | Default location |
| --- | --- |
| Database | `tei_database.db` in the project root (parent of the installed package) |
| Full-text HTML | `lemmaTEIbrowser/static/texts` |
| Templates | `lemmaTEIbrowser/templates` |
| JavaScript and CSS | `lemmaTEIbrowser/static` |

For a database already imported inside `DiSMIdataset`, run from the project root:

```bash
lemma-serve --db-path ./DiSMIdataset/tei_database.db
```

**Explicit relative paths are relative to the terminal's current directory.**
From any other directory, use an absolute path, for example:

```bash
lemma-serve --db-path "$HOME/Desktop/lemmaTEIbrowser/DiSMIdataset/tei_database.db"
```

To choose your own database and HTML directory, use the same paths for both commands:

```bash
lemma-import ./DiSMIdataset/tei-xml --db-path ./my_database.db --html-dir ./my_texts
lemma-serve --db-path ./my_database.db --html-dir ./my_texts
```

Alternatively, set `DATABASE_PATH` and `TEXT_HTML_DIR` environment variables.
CLI options take priority over environment variables, which take priority over
the defaults. `~` is expanded and paths are resolved to absolute paths.
Use a filesystem path for `--db-path` or `DATABASE_PATH`, not a `sqlite:///` URL.
Both commands print their resolved database and HTML locations;
`lemma-serve` also prints template and static-asset locations. It reports a
missing database instead of creating an empty one, and warns if the selected
database contains no words. SQLite needs an existing
parent directory and permission to write database journal files there.

Changing the selected database does not import data or regenerate HTML.
Reimporting the same files currently adds duplicate entries, so do not reimport
just to switch the server to an existing database.

# 

Ricerca per lemma:
http://localhost:5000/?q=verso&type=lemma
Per `verso` trova:
<w lemma="verso" xml:id="w1">versi</w> 
<w lemma="verso" xml:id="w1">verso</w> 


Ricerca per forma nomalizzata frasema:
http://localhost:5000/?q=versi rotti&type=phraseme
Con `versi rotti` trova:
<span n="versi rotti" target="#w1 #w3"/>
e le parole nel target.

Ricerca per lemma e forma normalizzata frasema (AlternativeLabel):
http://localhost:5000/?q=parti_discorso&type=alternativeLabel

Con `verso` trova:
<w lemma="verso" xml:id="w1">versi</w> 
<w lemma="verso" xml:id="w1">verso</w> 

Con `versi rotti` trova:
<span n="versi rotti" target="#w1 #w3"/>
e le parole nel target.

Ricerca per occorrenza:
http://localhost:5000/?q=versi&type=occurrence

Trova `versi` trova:
<w lemma="verso" xml:id="w1">versi</w> 

Ma non:
<w lemma="verso" xml:id="w1">verso</w> 

Ricerca per concetto:

http://localhost:5000/?q=verso&type=concept

Con `verso` trova:
<w ana="https://dismi/verso" lemma="linea" xml:id="w1">linee</w> 

Ma non:
<w ana="https://dismi/obbiettivo" lemma="verso" xml:id="w1">verso</w> 
