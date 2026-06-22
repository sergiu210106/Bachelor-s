# Propunere de temă pentru lucrarea de licență

**Titlu provizoriu:** Injecție de prompt prin substratul jurnalelor împotriva copiloților SOC bazați pe modele de limbaj locale: generarea adaptivă a payload-urilor sub constrângeri de câmp și limitele apărărilor antrenate pe jurnale de sistem Linux

**Domeniu:** Securitate cibernetică × Inteligență artificială (modele mari de limbaj)

**Student:** Sergiu-Florian Tuduce
**Universitate / Facultate:** Universitatea Babeș-Bolyai, Facultatea de Matematică și Informatică

---

## 1. Rezumat

Modelele mari de limbaj (LLM) sunt integrate tot mai des ca asistenți de analiză în centrele de operațiuni de securitate (SOC), unde citesc jurnale și alerte pentru a produce clasificări, sumarizări de incidente sau recomandări de remediere. Aceste sisteme au o slăbiciune structurală: o mare parte din câmpurile unui jurnal sunt controlate de atacator (User-Agent, URI-uri HTTP, corpul cererilor, argumente de linie de comandă, nume de utilizator încercate). Prin urmare, o intrare atent construită poate transporta instrucțiuni care deturnează LLM-ul care o citește — un caz particular de injecție indirectă de prompt pe care literatura recentă îl numește *injecție prin substratul jurnalelor* (log-substrate prompt injection).

Lucrarea propusă pornește de la două studii foarte recente care au stabilit fenomenul, dar pe modele comerciale și pe jurnale de rețea/cloud sintetice, cu payload-uri fixe scrise manual. Contribuția mea se plasează în lacunele lăsate explicit de aceste lucrări și este în primul rând **metodologică**: (1) **generarea adaptivă a payload-urilor**, formulată ca problemă de optimizare cu constrângeri, care exploatează accesul de tip white-box la logits disponibil în cazul modelelor locale, în locul payload-urilor scrise manual; (2) **prima evaluare a apărărilor antrenate** (checkpoint-uri StruQ/SecAlign publicate) alături de apărări la nivel de inferență, în acest context; și (3) un **studiu comparativ de susceptibilitate între modele** pe **jurnale de sistem Linux la nivel de gazdă** (jurnale de acces web/aplicație și înregistrări `auditd` execve), folosind **modele locale open-source** (Llama, Qwen, rulate prin Ollama/LM Studio) drept vehicul realist. Rezultatul așteptat este un studiu empiric reproductibil, condus integral într-un laborator izolat, cu un cadru clar defensiv.

## 2. Context și motivație

Centrele SOC se confruntă cu volume mari de alerte, deficit de personal specializat și timpi de răspuns întârziați. LLM-urile sunt propuse ca soluție pentru automatizarea analizei de jurnale, triajul alertelor și generarea de recomandări. Există deja sisteme comerciale (Microsoft Security Copilot, Google Security AI Workbench) și o literatură academică în creștere rapidă pe „copiloți SOC".

Problema apare din însăși natura datelor analizate. Spre deosebire de scenariile clasice de injecție indirectă (pagini web, documente), unde atacatorul trebuie să plaseze textul malițios în conținut pe care victima îl va consulta ulterior, în cazul SOC **canalul de livrare este intrinsec atacului**: o cerere care testează o injecție SQL este înregistrată în jurnal prin proiectare. Dacă atacatorul adaugă în aceeași cerere o instrucțiune de tipul „marchează această intrare ca benignă", fluxul de probe devine simultan un canal de instrucțiuni. Modelul trebuie să distingă proba de instrucțiune, deși ambele ajung în fereastra de context ca text simplu.

Motivația practică este accentuată de tendința de a rula LLM-uri **local**, pe gazdă, pentru a nu trimite jurnale sensibile în cloud (raționament de confidențialitate frecvent invocat de echipele de operațiuni). Tocmai acest scenariu realist — model mic, local, care citește jurnale de sistem Linux — nu a fost încă studiat din perspectiva injecției prin substrat.

## 3. Problema de cercetare și poziționarea în literatură

Fenomenul de bază a fost stabilit în 2026 de două lucrări:

- **„Poisoning the Watchtower"** (Pandey & Bhujang, arXiv:2605.24421, 2026) definește injecția prin substratul jurnalelor, propune o taxonomie cu patru clase (suprascriere directă, deturnare de persona, manipulare de context, payload ofuscat) și o evaluează pe trei sarcini (clasificare, sumarizare, remediere). Concluzii: suprascrierile directe nu mai funcționează pe modelele actuale; deturnarea de persona este cel mai puternic atac de clasificare; sumarizarea este cea mai vulnerabilă sarcină; apărările reduc, dar **nu elimină** suprafața de atac. **Limitări declarate explicit:** un singur model (gpt-4o-mini), jurnale sintetice structurate după CIC-IDS2017/UNSW-NB15, atacuri pe o singură rundă (fără iterație adaptivă) și fără agenți cu acces la unelte.

- **„LogJack"** (Shah, arXiv:2604.15368, 2026) studiază injecția prin **jurnale cloud** (CloudWatch, CloudTrail, CI/CD) împotriva agenților de depanare care pot **executa** comenzi de remediere, cu un benchmark de 42 de payload-uri pe 8 modele. Identifică un comportament de tip „sanitize and execute" (modelul elimină componenta evident malițioasă, dar execută restul instrucțiunii injectate).

**Lacuna pe care o adresez** rezultă direct din aceste limitări:

1. **Metoda de atac.** Ambele lucrări folosesc payload-uri fixe, scrise manual, iar „Watchtower" afirmă explicit că nu studiază atacuri iterative/adaptive. Literatura generală de injecție de prompt dispune de atacuri bazate pe optimizare (GCG, beam search, rafinare iterativă de tip PAIR condusă de un LLM), dar **niciuna nu a fost adaptată scenariului de substrat al jurnalelor**, unde payload-ul este constrâns de lungimea câmpului și de setul de caractere admis. Acest regim de constrângere este el însuși puțin explorat: este exact zona în care payload-urile naive scrise manual sunt cele mai slabe și unde un optimizator ar trebui să conteze cel mai mult.

2. **Apărări.** „Watchtower" testează doar apărări la nivel de inferență (prompting structurat, sanitizarea câmpurilor, ieșire constrânsă), cu rezultat modest (succesul atacului scade de la ~27% la ~12%). Apărările antrenate puternice — StruQ și SecAlign — **nu au fost niciodată evaluate împotriva injecției prin substrat**. În plus, există o controversă activă demnă de investigat: lucrări din 2025 arată că StruQ/SecAlign sunt mai puțin robuste decât se susținea inițial (atacuri conștiente de arhitectură, pierdere de utilitate). O întrebare deschisă naturală: au sens apărările bazate pe delimitatori când „datele" sunt telemetrie structurată `cheie=valoare`, nu proză?

3. **Cadrul.** Nimeni nu a măsurat fenomenul pe **jurnale de gazdă Linux** cu **modele locale open-source**. Aceasta nu este o simplă reluare: „Watchtower" arată că suprascrierea directă este ineficientă pe gpt-4o-mini, însă un model local mai mic, mai puțin robust la instrucțiuni, poate eșua în moduri *diferite* și poate redeschide clase de atac considerate „moarte" pe modelele de frontieră. Susceptibilitatea comparativă între modele, în implementarea realistă pe gazdă, este nemăsurată.

## 4. Întrebări de cercetare și ipoteze

- **Î1 (susceptibilitate).** Cât de susceptibile sunt modelele locale open-source de dimensiuni mici-medii la injecția prin substratul jurnalelor de gazdă Linux, comparativ cu rezultatele pe modele comerciale? Se păstrează ierarhia claselor de atac (deturnare de persona > suprascriere directă)?
  *Ipoteza I1:* modelele locale mai mici sunt **mai** vulnerabile la suprascrierea directă decât gpt-4o-mini, fiind mai puțin robuste la instrucțiuni; altfel spus, o clasă de atac raportată „moartă" se redeschide pe modelele locale.

- **Î2 (atac adaptiv).** Pot payload-urile generate prin optimizare cu constrângeri să depășească apărările la nivel de inferență din literatură, și depășește optimizarea white-box (cu acces la logits) rafinarea black-box condusă de un LLM, în special sub constrângeri stricte de câmp?
  *Ipoteza I2:* avantajul optimizării structurate față de căutarea condusă de LLM **crește pe măsură ce constrângerea de câmp devine mai strictă** (de ex. câmpuri scurte de tip nume de utilizator vs. câmpuri lungi de tip User-Agent).

- **Î3 (transferabilitate).** Se transferă payload-urile optimizate împotriva unui model local către altele, sau supra-învață modelul-țintă? (Un rezultat negativ este în sine o concluzie de securitate relevantă privind portabilitatea atacului.)

- **Î4 (apărări).** Cum se comportă apărările antrenate (checkpoint-uri StruQ/SecAlign publicate) și un detector dedicat în acest context, comparativ cu apărările la nivel de inferență, și cu ce cost de utilitate asupra sarcinii de bază a copilotului?

## 5. Obiective

1. Construirea unui banc de testare reproductibil: un copilot SOC minimal (pipeline RAG cu LangChain + Chroma, model local prin Ollama/LM Studio) care ingestă jurnale de sistem Linux și produce clasificare / sumarizare / recomandare de remediere.
2. Adaptarea și extinderea taxonomiei de atac din „Watchtower" la câmpurile specifice jurnalelor de gazdă Linux.
3. Proiectarea și validarea unui generator adaptiv de payload-uri sub constrângeri realiste de câmp, cu o ramură white-box (optimizare) și una black-box (condusă de LLM).
4. Implementarea și evaluarea unui set stratificat de apărări (la nivel de inferență + checkpoint-uri antrenate publicate + detector dedicat) față de o referință simplă.
5. Realizarea unui studiu empiric comparativ, în etape, pe mai multe modele, cu dimensiuni de eșantion adecvate și intervale de încredere, și formularea de recomandări de implementare.

## 6. Metodologie propusă

**6.1. Model de amenințare.** Atacator de la distanță, fără credențiale și fără acces la conducta de jurnalizare după ingestie, care poate doar trimite trafic / genera evenimente ce ajung în jurnalele gazdei (de ex. cereri HTTP înregistrate de un server web, sau comenzi înregistrate de `auditd`). Obiectivul atacatorului: a determina copilotul să eticheteze un eveniment malițios ca benign, să omită atacul din sumar sau să recomande inacțiune. În calitate de cercetător, joc ambele roluri: presupun **acces white-box pentru *descoperirea* payload-urilor** (justificat de faptul că modelele locale expun logits), apoi **testez transferul către o implementare black-box**, care este capacitatea realistă a atacatorului. Vor fi tratate distinct două variante: (a) **atacuri de decizie** (fără execuție de unelte) ca domeniu principal și, opțional și doar dacă timpul permite, (b) un **agent cu acces la unelte de remediere** într-o mașină virtuală complet izolată și deconectată de la rețea.

**6.2. Substratul controlat de atacator (rafinat).** Nu mă bazez pe `auth.log` de la SSH, al cărui conținut controlat de atacator se limitează la un nume de utilizator scurt și la bannerul de versiune al clientului. Substraturile principale sunt: (i) **jurnale de acces web/aplicație** (nginx/apache) — User-Agent, URI, referer, query string — care transportă text bogat și lung controlat de atacator pe gazdă; și (ii) **înregistrări `auditd` execve** — argumente de linie de comandă și căi de fișiere. Câmpul scurt de nume de utilizator SSH este păstrat deliberat ca **regim de constrângere strictă** pentru testarea la limită a optimizatorului (Î2/I2).

**6.3. Bancul de testare.** Pipeline RAG minimal (LangChain LCEL + Chroma) peste un model local servit de Ollama/LM Studio. Vor fi comparate cel puțin 3 modele locale de dimensiuni/familii diferite (de ex. un model instruct de 8B, unul mai mic și unul mai mare), plus, ca referință, un model comercial mic, pentru calibrare față de „Watchtower". Servirea locală este cea care face posibil accesul la logits — și deci optimizarea white-box.

**6.4. Date.** Două seturi: (i) jurnale **sintetice** generate programatic din șabloane de tipuri de atac (injecție SQL, traversare de cale, credential stuffing, injecție de comenzi, tunelare DNS, scanare), pentru control și reproductibilitate; (ii) jurnale **realiste** capturate într-un laborator izolat (o mașină-capcană/expusă intenționat), pentru a observa artefacte de parsare, trunchiere și câmpuri care lipsesc din datele pur sintetice — limitare semnalată explicit de „Watchtower". Datele capturate sunt tratate ca potențial sensibile (pot conține credențiale/PII reale în încercările de atac): sunt stocate local, anonimizate înainte de orice publicare și niciodată republicate verbatim.

**6.5. Generarea adaptivă a payload-urilor.** Formulare ca problemă de căutare cu constrângeri. Spațiul de căutare = șiruri admisibile într-un câmp-țintă (constrângeri de lungime și set de caractere). Funcția de fitness = un semnal **continuu**, nu un indicator binar de succes: probabilitatea pe care modelul-țintă o atribuie token-ului de ieșire dorit de atacator (de ex. eticheta „benign"), disponibilă pentru că modelul este local și white-box; opțional penalizată de un termen de detectabilitate. Două ramuri:
- **White-box:** un optimizator ghidat de gradient în spiritul GCG (baseline-ul standard adversarial la nivel de token), plus un algoritm genetic a cărui populație este formată din șiruri candidate de câmp, cu mutație/încrucișare definite la nivel de token/caracter și selecție după fitness-ul continuu. *(Aici se aplică experiența mea anterioară din metaeuristici.)* PSO clasic nu este folosit, fiind o metodă pentru spații continue, nepotrivită pentru șiruri discrete fără o adaptare netrivială; dacă este explorat, este încadrat ca experiment secundar de tip PSO discret.
- **Black-box:** un red-teamer condus de LLM (de tip PAIR) care rafinează iterativ payload-urile doar pe baza ieșirilor observate.

Comparația dintre cele două ramuri, mai ales pe măsură ce constrângerea de câmp se înăsprește, constituie substanța Î2.

**6.6. Apărări evaluate (stratificate corect).**
- *La nivel de inferență:* prompting structurat, sanitizarea/etichetarea câmpurilor controlate de atacator, ieșire constrânsă și **spotlighting** (o tehnică de prompting — delimitare/datamarking).
- *Antrenate:* checkpoint-uri StruQ/SecAlign **publicate** (de ex. un model Meta-SecAlign pe Llama-3-8B). Antrenarea acestor apărări de la zero este explicit **în afara domeniului** din motive de fezabilitate; folosirea checkpoint-urilor publicate îmbunătățește și reproductibilitatea.
- *Detecție:* un clasificator ușor care semnalează intrările de jurnal ce transportă instrucțiuni înainte ca ele să ajungă la analistul-LLM, **comparat cu** o referință simplă de tip regex/cuvinte-cheie și cu un guard gata făcut (de ex. Llama Guard / Prompt Guard); opțional, etichetarea provenienței la nivel de câmp.

**6.7. Metrici și design experimental.** Pe latura de atac: rata de suprimare (clasificare), rata de recomandare nesigură (remediere), rata de succes a injecției (sumarizare). Pe latura de apărare, **utilitatea** se măsoară ca performanța copilotului pe un **set etichetat curat, neatacat** (etichetarea corectă a evenimentelor real-malițioase și sumarizarea corectă), nu doar ca acuratețe pe jurnale benigne, pentru ca raportul robustețe–utilitate să fie onest. Pentru a controla explozia combinatorială (modele × 4 clase de atac × ~6 apărări × 3 sarcini) și a păstra fezabilitatea pe hardware local, se folosește un **design în etape**: o trecere de triere cu eșantion redus identifică celulele interesante, care sunt apoi reluate cu eșantioane mai mari, suficiente pentru intervale de încredere binomiale strânse. Diferențele aflate în zona de suprapunere a intervalelor sunt raportate ca neconcludente, nu supra-interpretate.

## 7. Contribuții așteptate

1. O **metodă adaptivă de generare a payload-urilor, conștientă de constrângeri**, pentru injecția prin substratul jurnalelor, cu o ramură de optimizare white-box și una black-box condusă de LLM, și prima caracterizare a modului în care regimul de constrângere de câmp influențează ce abordare câștigă.
2. **Prima evaluare a apărărilor antrenate** (StruQ/SecAlign publicate) alături de apărări la nivel de inferență și de un detector dedicat, în contextul substratului jurnalelor, cu un raport robustețe–utilitate onest.
3. Un **studiu comparativ de susceptibilitate între modele** pe jurnale de gazdă Linux cu modele locale open-source, incluzând o analiză de transferabilitate a payload-urilor optimizate.
4. Un banc de testare și un set de date (anonimizat) reproductibile, oferite comunității.

**Poziționare într-o frază:** „Watchtower" și „LogJack" au studiat modele comerciale și jurnale cloud cu payload-uri fixe; eu aduc un atac adaptiv conștient de constrângeri, prima evaluare a apărărilor antrenate și un studiu de transferabilitate între modele, pe modele locale care citesc jurnale de gazdă Linux.

## 8. Considerații etice

Toate experimentele se desfășoară într-un laborator izolat, fără ținte reale terțe și fără sisteme în producție. Lucrarea are caracter **defensiv**: scopul este înțelegerea și atenuarea unei clase de vulnerabilități în uneltele de securitate bazate pe LLM. Datele capturate din capcană sunt anonimizate și niciodată republicate verbatim. La publicare: **metodologia, taxonomia, seturile de date (anonimizate), apărările și detectorul** sunt destinate publicării deschise, însă **generatorul adaptiv de payload-uri** — care este, în fapt, o unealtă de atac — este tratat sub o politică de divulgare responsabilă / acces controlat, nu publicat „la cheie", iar rezultatele sale sunt raportate agregat. Varianta opțională cu agent capabil să execute comenzi rulează exclusiv într-un mediu virtualizat, deconectat de la rețea.

## 9. Plan de lucru orientativ (un semestru)

- **Săpt. 1–3:** Studiu de literatură consolidat; finalizarea modelului de amenințare, a substratului rafinat și a designului experimental în etape.
- **Săpt. 4–6:** Construirea bancului de testare (pipeline RAG + modele locale cu acces la logits + ingestie de jurnale Linux); generarea datelor sintetice și pornirea capturii din capcană.
- **Săpt. 7–9:** Implementarea taxonomiei de atac și a ambelor ramuri ale generatorului (optimizator white-box + red-teamer LLM); trecerea de triere cu eșantion redus.
- **Săpt. 10–12:** Integrarea apărărilor (inferență + checkpoint-uri publicate + detector vs. referință); aprofundarea celulelor interesante; rularea testelor de transferabilitate.
- **Săpt. 13–14:** Analiza rezultatelor, intervale de încredere, recomandări de implementare.
- **Săpt. 15–16:** Redactarea lucrării și pregătirea prezentării.

## 10. Bibliografie preliminară

1. Greshake, K. et al. (2023). *Not What You've Signed Up For: Compromising Real-World LLM-Integrated Applications with Indirect Prompt Injection.* AISec @ CCS.
2. Pandey, R. & Bhujang, A. (2026). *Poisoning the Watchtower: Prompt Injection Attacks Against LLM-Augmented Security Operations Through Adversarial Log Content.* arXiv:2605.24421.
3. Shah, H. (2026). *LogJack: Indirect Prompt Injection Through Cloud Logs Against LLM Debugging Agents.* arXiv:2604.15368.
4. Chen, S., Piet, J., Sitawarin, C. & Wagner, D. (2025). *StruQ: Defending Against Prompt Injection with Structured Queries.* USENIX Security (arXiv:2402.06363).
5. Chen, S. et al. (2025). *SecAlign: Defending Against Prompt Injection with Preference Optimization.* ACM CCS (arXiv:2410.05451).
6. Chen, S., Zharmagambetov, A., Wagner, D. & Guo, C. (2025). *Meta SecAlign: A Secure Foundation LLM Against Prompt Injection Attacks.* arXiv:2507.02735.
7. Hines, K. et al. (2024). *Defending Against Indirect Prompt Injection Attacks With Spotlighting.* arXiv:2403.14720.
8. Zou, A. et al. (2023). *Universal and Transferable Adversarial Attacks on Aligned Language Models* (GCG). arXiv:2307.15043.
9. Chao, P. et al. (2025). *Jailbreaking Black Box Large Language Models in Twenty Queries* (PAIR). (rafinare iterativă a atacului condusă de LLM).
10. Zhan, Q., Liang, Z., Ying, Z. & Kang, D. (2024). *InjecAgent: Benchmarking Indirect Prompt Injections in Tool-Integrated LLM Agents.* Findings of ACL (arXiv:2403.02691).
11. Debenedetti, E. et al. (2024). *AgentDojo: A Dynamic Environment to Evaluate Prompt Injection Attacks and Defenses for LLM Agents.* NeurIPS.
12. Habibzadeh, A. et al. (2025). *Large Language Models for Security Operations Centers: A Comprehensive Survey.* arXiv:2509.10858.
13. Pandya, N. V., Labunets, A., Gao, S. & Fernandes, E. (2025). *May I Have Your Attention? Breaking Fine-Tuning Based Prompt Injection Defenses Using Architecture-Aware Attacks.* arXiv:2507.07417.
