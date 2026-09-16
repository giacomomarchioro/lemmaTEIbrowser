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
lemma-import ./tei-xml-ids
```
After the import is completed we use the command:

```
lemma-serve 
```
To run the application. The application will be available at http://127.0.0.1:5000.

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
http://localhost:5000/?q=versi&type=occurence

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
