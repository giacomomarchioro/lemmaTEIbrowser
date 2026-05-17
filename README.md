# lemmaTEIbrowser
A tool for creating databases of lemmas from a folder containing TEI files.





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