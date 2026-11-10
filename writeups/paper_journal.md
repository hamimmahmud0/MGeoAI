**MGeoAI: Extracting Road-Accident Facts and Recognizing Repeated Reports of the Same Accident in Online News with Large Language Models**

Hamim Mahmud, S.M. ASCE^1^; Oishik Majumder, S.M. ASCE ^2^; Mubasshir Bin Shahid, S.M. ASCE ^3^; Md. Azijul Islam, M. ASCE, Ph.D.^4^; and Shofiq Ahmed^5^

¹B.Sc. Student, Department of Civil Engineering, Bangladesh University of Engineering and Technology (BUET), Dhaka 1000, Bangladesh. Email: [2104065@ce.buet.ac.bd](mailto:2104065@ce.buet.ac.bd)

² B.Sc. Student, Department of Civil Engineering, Bangladesh University of Engineering and Technology (BUET), Dhaka 1000, Bangladesh. ORCID: https://orcid.org/0009-0006-4530-1992. Email: [oishikm76@gmail.com](mailto:oishikm76@gmail.com)

³ B.Sc. Student, Department of Civil Engineering, Bangladesh University of Engineering and Technology (BUET), Dhaka 1000, Bangladesh Email: [mubasshirbinshahid3@gmail.com](mailto:mubasshirbinshahid3@gmail.com)

^4^ Assistant Professor, Department of Civil Engineering, Bangladesh University of Engineering and Technology (BUET), Dhaka 1000, Bangladesh. ORCID: https://orcid.org/0000-0003-2603-7031. Email: [azijul@ce.buet.ac.bd](mailto:azijul@ce.buet.ac.bd)

^5^Shofiq Ahmed, Executive Vice President, Peggy Malone & Associates. Email: <sahmed@peggymalone.com>

ABSTRACT

News reports are a timely source of road-accident information where official crash records are delayed or incomplete, but a single accident is commonly covered by several outlets in different languages and with revised casualty figures. This study evaluates large language models (LLMs) on a hand-annotated corpus of 244 news articles describing 100 road accidents (124 articles from Bangladesh and 120 from other countries, in English and Bengali) for two tasks: (i) extraction of structured accident facts from a single article, and (ii) identification of articles that report the same accident. Extraction was scored against blind human annotation, for three models of increasing economy (DeepSeek, a 4-bit Qwen3.8-27B, and the 1.7-billion-parameter edge model LFM3-1.7B) and for reasoning switched on and off. With article text and publication timestamp as input and reasoning on, DeepSeek matched the reference number of fatalities in 97.8% of 231 single-accident articles (95% bootstrap interval 95.9% to 99.6%) and the country in 97.4%; day-level date agreement rose from 63.3% to 81.0% when the timestamp was supplied. Switching reasoning off made DeepSeek about five times faster and improved the killed-plus-injured total by 4.2 percentage points but lowered the date score by 4.7 points and the share of valid answers from 100% to 91.8%. Qwen was 14.7 percentage points lower on the killed-plus-injured total. The edge model returned a valid answer for only {{runs.lfm.okpct}} of articles. For same-accident identification, evaluated on 973 labeled article pairs re-weighted to all 29,646 pairs, DeepSeek clustering of short article summaries recovered all 100 accidents exactly and full-article pair judgment attained an F1 score of 99.6%, compared with 54.1% for multilingual sentence embeddings, 66.1% for a rule on extracted fields, and 29.3% for word similarity. An error analysis attributes most extraction errors to dates left empty, injured persons omitted from totals, and additional vehicles listed. The reference groups were assembled with an AI agent and verified by three of the authors. The dataset, code, and a script that regenerates all reported results are public.

# 1. INTRODUCTION

Road traffic injury remains a leading global public-health and transportation-safety problem, with an estimated 1.19 million deaths in 2021 (World Health Organization 2023). Crash-data systems that support hazard diagnosis, countermeasure evaluation, and emergency planning are, however, uneven across countries. Police-based records may be delayed or incomplete, and in many low- and middle-income settings they are not available in machine-readable form. Online news can complement these records: outlets typically report an accident within hours and state the number of casualties, the vehicles involved, and the place.

Two methodological problems must be resolved before news reports can be used as accident data. The first is *extraction*: converting the free text of one article into a structured record whose errors, such as an incorrect fatality count, propagate into any downstream statistics. The second is *repeated reporting*: because the same accident is covered by several outlets, often in different languages and with different, evolving details, articles must be linked to the accident they describe, or the accident will be counted several times. The first problem relates to information extraction with LLMs (Xu et al. 2024; Schwitter 2025), the second to cross-document event coreference (Leban et al. 2014; Gao et al. 2024; Nath et al. 2024). Prior transportation studies have mined newspapers for crash data (Bhuiyan et al. 2022; Chowdhury et al. 2024) and applied LLMs to crash narratives (Mumtarin et al. 2023), but, to our knowledge, none has reported field-level agreement with independent human annotation on news in two languages, nor compared LLM and non-LLM methods for linking multilingual reports of the same accident.

An earlier version of this work evaluated a rule-based and LLM-assisted pipeline on six incidents. That evaluation was too small to support conclusions about matching accuracy. The present study replaces it with a corpus of 244 articles, blind human annotation, a frozen sample of 973 labeled article pairs, and a simpler pipeline in which the LLM reads the article directly. It addresses four research questions:

1. How closely do LLM extractions agree with human annotation, field by field?
2. How do the publication timestamp, article images, and the model's reasoning mode affect extraction?
3. How accurately can an LLM identify articles that report the same accident, and how does it compare with embedding-based and rule-based alternatives?
4. How far can extraction be pushed toward low-cost operation, with reasoning switched off and with a 1.7-billion-parameter edge model?

The contributions are (a) a public dataset with 328 annotations, 947 model extraction records, 973 labeled article pairs, and 100 accident groups, released without article text for copyright reasons; (b) a field-level evaluation of DeepSeek and Qwen against the human reference, with chance-corrected agreement; (c) a comparison of eight methods for same-accident identification, including pair judging, clustering, multilingual embeddings, word similarity, and a field rule; and (d) a script that regenerates every reported number from the public data. The system fuses reported evidence; it does not establish truth or fault.

# 2. RELATED WORK

## 2.1 Traffic Incident Detection and News-Based Crash Data

Social-media text has been shown to complement physical traffic detectors. Gu et al. (2016) developed real-time incident detection from Twitter posts, Ali et al. (2021) combined social-network data with accident detection and condition analysis, and AlDhanhani et al. (2023) showed that combining heterogeneous signals improves traffic-event detection. These studies focus on detecting or classifying events rather than on reconciling several reports of one event. Newspapers have also been used directly as a crash-data source in Bangladesh: Bhuiyan et al. (2022) compiled 441 crashes reported in three newspapers for 2019 for severity analysis, noting a bias toward severe crashes, and Chowdhury et al. (2024) combined web scraping with LLMs to generate a Bangladeshi accident dataset, comparing GPT-4, GPT-3.5, and Llama-3 on 195 manually annotated reports. The present study extends this line to a second language, to reports from outside Bangladesh, to a human-agreement benchmark, and to the linking of repeated reports.

Under-reporting is the reason such alternative sources matter. Police files capture only part of road casualties: in one French county only about 38% of casualties in a trauma registry appeared in police records, with slight injuries and motorcyclists least covered (Amoros et al. 2006), and in Queensland, Australia, about two-thirds of road crash injuries in hospital data did not link to any police record (Watson et al. 2015). News reports can fill part of the gap: in Yaoundé, Cameroon, newspapers recorded 480 road traffic injuries, against 273 in police records and 1,686 in a hospital trauma registry, and they captured mass-casualty events that the other sources missed (Juillard et al. 2017).

## 2.2 LLMs for Information Extraction

Generative information extraction uses LLMs to map free text to entities, events, and structured fields (Xu et al. 2024). Schwitter (2025) demonstrated that LLMs can extract predefined information from noisy historical newspaper text, and Grigorev et al. (2025) combined LLM-derived features with conventional machine learning to classify traffic-incident severity. Mumtarin et al. (2023) compared ChatGPT, BARD, and GPT-4 on 100 police crash narratives and found that agreement among the models was highest for direct yes-or-no questions and lower for complex ones. These studies motivate our extraction evaluation, which differs in using independent human annotation of news articles in two languages and in reporting chance-corrected agreement. Work in transportation safety now applies LLMs widely: Zhen et al. (2024) used chain-of-thought prompting with GPT-3.5 and LLaMA3 models to infer crash severity from narratives, and Wandelt et al. (2024) reviewed more than 130 papers on LLMs for intelligent transportation, including safety.

## 2.3 Linking Reports of the Same Event

Event coreference is the task of deciding whether two documents describe the same real-world event. News systems have long clustered related stories (Leban et al. 2014); more recent work formalizes cross-document event extraction (Gao et al. 2024) and incorporates visual information into event coreference (Nath et al. 2024). Multimedia event extraction has shown that images can contribute information absent from text (Li et al. 2020), and multimodal language models have been applied to crash video (Zhang et al. 2025). A common non-LLM approach to document linking is sentence embedding, in which a text is mapped to a vector and similarity is measured by cosine. Multilingual models such as LaBSE (Feng et al. 2022) and multilingual E5 (Wang et al. 2024) place different languages in one space (see also Reimers and Gurevych 2019). Bengali is a comparatively low-resource language for which dedicated pretrained models were required to approach English-level performance (Bhattacharjee et al. 2022). We include embedding similarity as the principal non-LLM baseline.

# 3. DATA AND METHODS

Figure 1 summarizes the design. Each article is processed along two independent paths: an LLM extracts a fixed set of fields, and a human annotator, blind to model output, records the same fields. The two records are compared field by field. A separate experiment evaluates methods for identifying articles that report the same accident.

@@FIG1@@

## 3.1 Corpus

One hundred road accidents were selected, 50 from Bangladesh and 50 from other countries. Candidate articles for each accident were located by web search, assisted by a browser-based AI agent, and each group of articles was then verified by three of us (the annotating authors). For each article, the publisher and URL, the publication date and time, a markdown rendering of the article portion of the HTML page, and all article images were saved. The corpus comprises 244 articles from 102 publishers (208 English, 36 Bengali; 124 Bangladeshi, 120 international). In each region, 30 accidents form the main set (typically three or four articles each, 192 articles in total) and 20 are look-alike accidents (one or two articles each, 52 in total) selected to be confusable with the main set; 236 articles carry at least one image, and 631 images were saved (@@T1@@).

@@T1@@

## 3.2 Input Preparation

HTML pages were cleaned by removing scripts, styles, forms, buttons, embedded frames, vector graphics, navigation bars, headers, footers, and sidebars, and were converted to markdown. Scripts were never executed. The publication timestamp found on the page was added in a labeled block with the instruction that it may be inaccurate, is not the accident date, and serves only to resolve relative dates. In the run that used images, up to three images per article were supplied, resized to a longest side of 1,024 pixels. The article text was delimited by `<ARTICLE_SOURCE>` markers and the prompt declared its content to be data, not instructions, as a mitigation against prompt injection. Annotator records and group membership were never provided to the extraction models.

## 3.3 Extraction Schema and Annotation

For each article, the model and each annotator judged whether the article was usable and reported a specific road accident and, for each accident, populated the fields in @@T2@@. Fields were left empty when the article did not state them; the prompt prohibited guessing and any inference of fault. The model additionally supplied, for each non-empty field, a quote copied verbatim from the article. For each image, the model and annotators stated whether the image shows the accident and described its content.

@@T2@@

Three of us annotated the articles from the original web pages without access to model output. Every article has at least one annotation. The reference is one annotation per article: that of the first annotator, in the fixed order A, B, C, who labeled the article (Annotator A wrote 166 of the 244 reference annotations, Annotator B 76, and Annotator C 2). All 244 reference annotations were judged usable: 240 describe one accident, three describe two, and one describes five. No annotation contains coordinates, so coordinates are not scored.

## 3.4 Model Runs

Each article was submitted in a single request containing the prompt (isolate the article body, decide whether it reports a specific road accident, fill the fields in @@T2@@, and return JSON only). All runs used temperature 0 and the same prompt. Configurations are named by model, followed in brackets by the inputs supplied (T, article text; P, publication timestamp; I, images) and, where it departs from the provider default, the reasoning mode (@@T3@@). Pairs of configurations differ in one factor: [T] versus [TP] isolates the timestamp, and reasoning on versus off isolates reasoning.

@@T3@@

The models span a range of cost. We accessed DeepSeek through the provider's API. We hosted Qwen3.8-27B ourselves in 4-bit (Q4) quantized form, and likewise LFM3-1.7B, a 1.7-billion-parameter model intended for edge deployment, on two NVIDIA T4 GPUs; we served both behind OpenAI-compatible endpoints, each processing two requests at a time. The DeepSeek output limit was set to the provider maximum so that reasoning could not truncate an answer; observed use was about 2,900 output tokens per article with reasoning on and about 450 with reasoning off. A free MiniMax model accessed through OpenRouter completed only 72 articles because of service limits and is not reported.

@@LFMREASON@@

Output was accepted only if it conformed to the schema (field names, ranges, date format, vehicle vocabulary) and each evidence quote occurred verbatim in the article. Calls that violated these rules or were truncated at the output limit were counted as failures of the model and were not retried or repaired. Network timeouts, which arose because the tunnel in front of the authors' server closes a request after 100 seconds, were repeated and are not counted as model failures. No fallback to another model was applied.

## 3.5 Same-Accident Identification

Two articles were defined as reporting the same accident when they describe the same crash (same vehicles, place, and time); they may differ in language, wording, detail, and casualty figures. Two crashes of the same kind on the same road, in the same city, or on the same day are different accidents unless the details match. Eight methods were compared (@@FIG2@@).

@@FIG2@@

*Pair judge, full articles.* The LLM receives two articles (publisher, date, title, first 12,000 characters) and returns one of four labels (same accident, different accident, related but distinct, uncertain), a confidence, quotes, and a two-sentence rationale.

*Pair judge, extracted fields.* The LLM receives only the publication date and extracted fields (killed, killed plus injured, vehicles, date, country, location) for each article, taken from the annotator, the model, or both.

*Clustering.* The LLM receives all 244 articles in one request and partitions them. Each article is a card with an opaque identifier (A001, A002, ...), presented in an order shuffled with a fixed seed. In the short-card variant a card contains publisher, date, title, the first 350 characters, and the extracted fields; in the full-text variant it contains the first 4,000 characters and no extracted fields. Each variant was run three times with different shuffles, and the consensus links two articles that were co-clustered in at least two runs.

*Embedding similarity.* Each article (title and first 1,500 characters) is embedded with LaBSE (Feng et al. 2022) or multilingual E5 base (Wang et al. 2024), and pairs are compared by cosine similarity against a threshold. The threshold was either tuned on the whole sample or learned on the other four fifths of the accident groups and applied to the held-out fifth.

*Word similarity.* TF-IDF weights words by log term frequency and smoothed inverse document frequency; the title and first 1,500 characters are compared by cosine against a threshold tuned on the whole sample.

*Field rule.* Two articles match when both report one accident, the countries are equal, the dates differ by at most one day, and the location word sets have Jaccard overlap of at least 0.3.

In pair judging each pair was queried twice, with the articles in both orders, and was called "same" only if both answers were "same accident"; this rule was fixed before any model call.

## 3.6 Pair Sample

All 232 same-accident pairs were included, together with 741 different-accident pairs drawn from four classes: look-alike accidents (163 pairs), same country and published within four days (128), most similar wording (300 of 350 candidates), and random pairs (150 of 28,773). The population comprises 29,646 pairs (@@FIG3@@). Because easy pairs are heavily under-sampled, scores are re-weighted to the full population (Equation 6). The sample, prompts, and decision rule were fixed and fingerprinted before any model call. All LLM same-accident methods used DeepSeek (temperature 0, thinking on); the field-based methods used the reference annotator's record and the DeepSeek [TP] extraction.

@@FIG3@@

## 3.7 Metrics

*Extraction.* For a field with reference value $y_{i}$ and model value ${\hat{y}}_{i}$ over $N$ articles, exact match is given by Equation 1 and, for counts, the mean absolute error (MAE) by Equation 2. Dates were compared by calendar day, countries after case folding, and vehicle lists as sets. Free text was compared by the Jaccard index of word sets $A$ and $B$ (Equation 3), also used for vehicle lists.

$$\text{Exact match} = \frac{1}{N}\sum_{i = 1}^{N}\mathbb{1}\left\lbrack {\hat{y}}_{i} = y_{i} \right\rbrack\qquad(1)$$

$$\text{MAE} = \frac{1}{N}\sum_{i = 1}^{N}\left| {\hat{y}}_{i} - y_{i} \right|\qquad(2)$$

$$J(A,B) = \frac{|A \cap B|}{|A \cup B|}\qquad(3)$$

Chance-corrected agreement on categorical fields was measured by Cohen's kappa (Equation 4), where $p_{o}$ is observed agreement and $p_{e}$ is agreement expected by chance; vehicle types were scored one type at a time by presence.

$$\kappa = \frac{p_{o} - p_{e}}{1 - p_{e}}\qquad(4)$$

Additional measures were accident-flag recall (all articles report an accident, so false alarms cannot be measured), agreement on the number of accidents, the share of evidence quotes found verbatim, and the valid-answer rate (the share of the 244 articles for which a conforming answer was obtained). Field scores were computed on every annotated article whose reference has one accident and for which the configuration returned one accident; the number of articles is reported for each configuration. Because a model that often violates the format may look accurate when scored only on its valid answers, end-to-end exact match counts an article without a valid answer as a miss over all 240 reference articles. Differences between configurations (@@T7@@) use the articles answered by both. Disagreements with the reference on killed plus injured, date, and vehicles were sorted into error types (@@T11@@).

*Same-accident identification.* Precision, recall, and F1 follow Equation 5, where TP, FP, and FN are true positives, false positives, and false negatives. Cluster quality was additionally assessed by the number of accidents recovered exactly, split, and wrongly merged.

$$P = \frac{TP}{TP + FP},\qquad R = \frac{TP}{TP + FN},\qquad F1 = \frac{2PR}{P + R}\qquad(5)$$

Each sampled pair stands for $w_{s}$ real pairs (Equation 6), where $N_{s}$ is the number of possible pairs of class $s$ and $n_{s}$ the number tested, and weighted counts enter Equation 5.

$$w_{s} = \frac{N_{s}}{n_{s}}\qquad(6)$$

*Uncertainty.* Ninety-five percent bootstrap intervals were obtained by resampling whole accident groups (2,000 resamples for extraction, 1,000 for same-accident identification), because articles on the same accident are not independent. Differences between runs were assessed with paired bootstrap intervals on per-article differences.

# 4. RESULTS

## 4.1 Reliability

With reasoning on, DeepSeek answered all 244 articles in both input settings (@@T4@@). With reasoning off it was considerably faster (median {{runs.deepseek_off.median_latency_s|f1}} s per article against {{runs.deepseek_date.median_latency_s|f1}} s) and wrote about one sixth of the output tokens, but only {{runs.deepseek_off.ok}} of 244 answers were valid ({{runs.deepseek_off.okpct}}); failures were answers without an accident object, vehicles outside the fixed list, and other format errors. Qwen answered 239 articles. The edge model produced a valid answer for {{runs.lfm.ok}} of {{runs.lfm.articles}} articles ({{runs.lfm.okpct}}), mainly failing on vehicle names outside the fixed list and other format violations. Between 92% and 98% of the evidence quotes of the larger models were verbatim, against 63% for the edge model.

@@T4@@

## 4.2 Field-Level Agreement

@@FIG4@@

Exact-match scores are given in @@T5@@ and @@FIG4@@, and chance-corrected agreement in @@T6@@.

@@T5@@

@@T6@@

Fatalities and country were extracted almost perfectly by the larger models (kappa 0.96 to 0.98 for fatalities and 0.96 to 0.97 for country; exact match 96.5% to 97.8% for fatalities, with a mean absolute error below 0.2 persons, and 97.0% to 97.8% for country). Killed-plus-injured agreement was about 75% for DeepSeek with reasoning on, 81.6% with reasoning off, and 60.2% for Qwen. Supplying the publication timestamp raised DeepSeek's day-level date agreement from 63.3% to 81.0% (19.2 percentage points on the articles answered in both settings; @@T7@@). Vehicle sets matched exactly in about 60% of articles (mean word overlap 0.74 to 0.77; mean kappa per vehicle type 0.74 to 0.77), and exact match of free-text location was about 3%, so word overlap (about 0.5) is the informative measure for location.

## 4.3 Effect of Reasoning

@@T7@@

Switching DeepSeek's reasoning off changed the killed-plus-injured total by +4.2 percentage points (paired interval 0.5 to 8.3) and the date by −4.7 points (interval −8.3 to −1.3), lowered the valid-answer rate from 100% to {{runs.deepseek_off.okpct}}, and made each answer about five times faster with about one sixth of the output tokens. Reasoning therefore chiefly purchased format reliability, not content accuracy, and the input (the timestamp, +19.2 points for the date) mattered more than the reasoning mode. Qwen, run with reasoning off, differed from DeepSeek [TP] clearly only on the killed-plus-injured total (−14.7 points, interval −22.6 to −6.8); because it differs from DeepSeek in size, quantization, and image input, this difference cannot be attributed to a single factor.

@@LFMREASON2@@

## 4.4 Edge Model

On the {{lfm.n}} articles for which LFM3-1.7B returned a valid answer, it matched the reference country in {{lfm.country}} and the number killed in {{lfm.killed}} of cases, but the killed-plus-injured total in only {{lfm.cas}} (@@T5@@). End-to-end exact match, counting articles without a valid answer as misses, was {{lfm.e2e_killed}} for the number killed and {{lfm.e2e_country}} for the country, against {{ds.e2e_killed}} and {{ds.e2e_country}} for DeepSeek [TP]. Most failures were format violations, chiefly vehicle names outside the fixed list, that a model-specific prompt, a simpler output format, a repair step, or fine-tuning might remove; none of these was added, because each would alter the task. Throughput on the authors' hardware was low (median {{runs.lfm.median_latency_s|f1}} s per valid article with two concurrent requests).

@@LFMGROUP@@

## 4.5 Region and Language

@@T8@@

Scores were higher for Bangladeshi than for international articles, notably for the date (90.0% against 71.2% for DeepSeek [TP]) and killed plus injured (80.0% against 69.4%) (@@T8@@). Bengali articles (36 for DeepSeek [TP]) scored as high as English articles, with every fatality count matching, although the sample is small.

## 4.6 Images

Of the 244 articles, 236 carry at least one image (631 images). Qwen [TPI] analyzed 480 images (at most three per article), and the reference annotators labeled 383. On the 352 images labeled by both, they agreed on whether the image shows the accident in 340 cases (96.6%; @@T9@@). Since the annotator judged 86.9% of these images to show the accident, precision (99.0%) and recall (97.1%) are the more informative measures. Only Qwen received images, so the effect of images on the text fields was not isolated.

@@T9@@

## 4.7 Same-Accident Identification

@@FIG5@@

@@T10@@

DeepSeek-based methods outperformed the alternatives that do not use an LLM (@@T10@@ and @@FIG5@@). Clustering with short cards recovered all 100 accidents exactly in all three runs; with full text, one accident was split in two of three runs, giving a consensus F1 of 99.6%. Together, the three runs of either clustering variant used about one fifteenth of the tokens of full-article pair judging. Full-article pair judging made no false match among the 741 different-accident pairs, including all 163 look-alike pairs, and found 230 of 232 same-accident pairs (recall 98.1% for the 54 English–Bengali pairs and 96.8% for the 62 pairs with different death tolls); the two query orders disagreed for 0.4% of pairs. Judging from extracted fields alone gave F1 between 95.8% and 98.9% with about 40% of the tokens; the model-only variant matched five of 163 look-alike pairs and one of 300 similar-wording pairs wrongly.

Embedding similarity reached an F1 of 58.3% (multilingual E5) and 38.9% (LaBSE) with a threshold tuned on the whole sample and 54.1% and 26.1% with a threshold learned on held-out folds. The mean cosine of English–Bengali pairs describing the same accident (0.87 for E5) equalled that of random pairs (0.87), and none of the 54 such pairs was matched by E5. The field rule was precise (99.1%) but recalled only 49.6% of same-accident pairs, and word similarity matched none of the English–Bengali pairs and wrongly matched 23 look-alike and 169 similar-wording pairs. Among the DeepSeek methods the intervals overlap.

## 4.8 Error Analysis

@@T11@@

Four patterns account for most extraction errors (@@T11@@). First, date errors are overwhelmingly omissions: 80 of 84 errors for DeepSeek [T] and 37 of 44 for DeepSeek [TP] are dates left empty, whereas a date that is given is almost always correct (off by one day in two to four articles); the prompt instructs the model to leave the date empty when it cannot be determined, the timestamp halves the omissions, and 37 remain because many articles do not state the date. Qwen omitted fewer dates (17) but produced more wrong ones (10 off by one day, 9 by more, and 2 equal to the publication day). The edge model erred in the opposite direction: of its 41 date errors only three were omissions, whereas 19 were off by more than one day and 16 equalled the publication day, as if the timestamp had been copied. Second, killed-plus-injured errors for DeepSeek are chiefly totals equal to the model's own killed count, meaning that injured persons were not added (18 to 20 articles), followed by lower totals (14 to 16); a further 16 disagreements arise because the reference annotator left the total empty, which occurs in 17 of the 240 reference annotations, whereas in 40 the reference total equals the number killed. Qwen's lower score reflects a different habit: it gave no total in 63 articles. For the edge model, 42 of 96 errors were totals equal to its killed count and 36 were lower totals. Third, in 46 to 48 of the 81 to 92 vehicle disagreements the model's list is a superset of the reference, most often adding trucks (19 articles), buses (12 to 14), and autorickshaws, whereas lists with vehicles left out account for 14 to 23, mostly microbuses and trucks; this suggests that the reference lists fewer vehicles than the models and explains the gap between exact match (about 60%) and word overlap (0.74 to 0.77). DeepSeek with reasoning on used the "other" option for 22 articles and with reasoning off for one. Fourth, the number of accidents disagrees with the reference in articles that report or mention more than one accident: the reference holds four such articles, whereas the models identified more accidents than the reference in 4 to 8 articles and fewer in 1 to 5. The only misses on the number of fatalities for DeepSeek were five articles (the model gave 4 where the reference gives 14, 51 for 79, and 30 for 31, and left the number empty where the reference gives 0 and 15).

Same-accident errors are few and fall into four types. (i) Roundup articles: the only accident missed by full-text clustering, and one of the two pairs missed by full-article pair judging, involve a news roundup reporting several crashes; in one case the judge answered "same" in one presentation order and "uncertain" in the other, so the both-orders rule labeled the pair "different". (ii) Source disagreement: judging from fields alone, the model decided that two reports of one crash were two crashes because the recorded roads, times, and vehicles differed; the article text is needed to recognize one report as a loose version of the other. (iii) Roundups in the model-only variant: the extracted record of a roundup contained a crash from another report and produced a false match. (iv) Topic rather than event: embedding and word similarity match articles about similar accidents, including two crashes from one website that share boilerplate text, and miss English–Bengali reports of one accident, which share neither words nor similar vectors.

# 5. DISCUSSION

Extraction accuracy depends on the field and on the input. Fatality counts and country were extracted almost perfectly by the larger models, and dates were reliable once the publication timestamp was supplied, with errors dominated by omission, not by wrong values. The killed-plus-injured total was the weakest field: models frequently left injured persons out of the sum, the reference annotator sometimes left the total empty, and Qwen often gave no total at all, which accounts for most of its 14.7-point deficit. Vehicles and locations are expressed in free wording, so exact match understates closeness. We therefore recommend supplying the publication timestamp, using a fixed vehicle vocabulary with an explicit rule on which vehicles to list, stating that the total must include injured persons, and scoring place names by word overlap or a lookup step.

Reasoning chiefly bought format reliability. DeepSeek with reasoning off was about five times faster and wrote about one sixth of the tokens; it was slightly better on killed plus injured and slightly worse on the date, but one answer in twelve violated the required format. Where cost and latency dominate, reasoning off combined with a repair step for format violations is a reasonable operating point.

The edge model illustrates the cost of economy. LFM3-1.7B ran on two modest GPUs, but about four answers in ten violated the required format, and end-to-end scores were far below those of the larger models. Because its failures were mostly of format, a model-specific prompt, a simpler output format, a repair step, or fine-tuning on this task could reduce them; the present results are best read as a baseline for such work, not as a ceiling.

For same-accident identification, DeepSeek-based methods were substantially more accurate than multilingual embeddings, word similarity, and a field rule. The embedding result is instructive: embeddings measure what an article is about, so reports of two different road accidents are as close as English and Bengali reports of one accident, and a single threshold cannot separate them. Clustering short article summaries in one request was both the most accurate and the least costly approach. For collections far larger than 244 articles, the articles would be partitioned first, for example by country and date window, so that each request fits the model's context; clustering followed by pair verification of doubtful groups would retain most of the accuracy at a small fraction of the cost. Querying each pair in both orders doubles cost but detected order-dependent answers in 0.4% of pairs.

The findings apply to extraction and same-accident identification on this corpus. They do not extend to public sentiment or global coverage, and the website's map points (Appendix A) are place centres rather than crash coordinates.

# 6. LIMITATIONS

The corpus is small and was assembled deliberately, so rates do not describe news coverage in general. A single annotation per article is the reference (chosen by a fixed annotator order), the annotators and group verifiers are among the authors, and all articles report an accident, so false alarms were not measured. The same-accident reference groups were assembled with an AI agent and verified by us, and several methods score near the ceiling, which limits fine ranking. Same-accident methods were run with DeepSeek, apart from the partial runs of the edge model. We ran Qwen quantized to 4 bits and differs from DeepSeek in several respects, so the effect of images alone was not isolated. We tested the edge model through a tunnel that limits each request to 100 seconds, with a small output limit and without repair of format violations, so its scores describe that setting. Map points were not evaluated against true coordinates. Provider models change over time, and article text is not shared because it belongs to the publishers.

# 7. CONCLUSION

On 244 news articles about 100 road accidents, DeepSeek extracted the number of fatalities (97.8%) and the country (97.4%) with near-perfect agreement in 231 single-accident articles and reached 81.0% day-level date agreement when given the publication timestamp, against 63.3% without it; it was weaker on vehicles and killed-plus-injured totals. Switching reasoning off made it about five times faster and 4.2 points better on the killed-plus-injured total, at the cost of 4.7 points on the date and a drop in valid answers from 100% to 91.8%. Qwen3.8-27B (4-bit) was similar except on killed-plus-injured totals, where it was 14.7 points lower, and the 1.7-billion-parameter edge model LFM3-1.7B returned a valid answer for {{runs.lfm.okpct}} of articles. For identifying articles that report the same accident, DeepSeek methods reached F1 scores of 95.8% to 100%, against 54.1% for multilingual embeddings, 66.1% for a field rule, and 29.3% for word similarity, and clustering of short summaries recovered all 100 accidents at about one fifteenth of the token cost of pair judging. An error analysis shows that most extraction errors are dates left empty, injured persons omitted from totals, and additional vehicles listed, and that most same-accident errors involve roundup articles. Future work should include automatic collection of accident news from sites that restrict automated access, a maintained list of accident-reporting domains, edge models of 1 to 4 billion parameters tuned for this task, with a suitable prompt and a repair step, evaluated against the larger models used here, methods for fusing the facts of several articles into one record, and a controlled test of images with one model run with and without them.

# APPENDIX A. PLACING AN ACCIDENT ON A MAP

Extraction yields no map coordinates. For the project website, an accident's position is assumed from its place name: after grouping, DeepSeek reads the first 3,500 characters of each article in a group and writes one place name from the most specific place to wider areas; the name is searched in OpenStreetMap Nominatim (OpenStreetMap contributors 2026), dropping the most specific component until a place is found; the accident is placed at the centre of that place, results that are only a country are discarded, and the radius is half the diagonal of the place's bounding box (minimum 0.3 km, maximum 300 km, with floors of 0.3, 2, 5, or 15 km for zero, one, two, or three or more dropped components). The radius expresses the size and vagueness of the matched place, not a statistical interval. Ninety-seven of 100 accidents were placed (median radius 11.4 km; 68 of 97 within 20 km). These points were not scored against true locations.

![Figure A1. The project website. Each circle is one grouped accident, coloured by people killed; selecting it opens the fused summary, the places where sources disagree, and the extracted fields, which can be switched between the reference annotation and each model's output.](figures/figA1_webapp.png){width=6.3in}

# DATA AVAILABILITY STATEMENT

The annotations, model extractions, same-accident labels and predictions, embedding scores, and incident summaries are available at https://huggingface.co/datasets/hamimmahmud0/mgeoai-road-accident-news under a CC BY 4.0 license (Mahmud et al. 2026). Article text and images are not included because they belong to the publishers; each article's URL is listed. The code, prompt, and scripts are available at https://github.com/hamimmahmud0/MGeoAI. The command `mgeoai x reproduce --dataset hamimmahmud0/mgeoai-road-accident-news --output reproduced/` regenerates the evaluation, and `writeups/paper_numbers.py` and `writeups/make_figures.py` regenerate the additional numbers and figures reported here. An interactive view is available at https://mgeoai.cartmind.xyz/.

# ACKNOWLEDGMENTS

This research received no specific grant from funding agencies in the public, commercial, or not-for-profit sectors. The authors acknowledge the publishers whose publicly accessible reporting enabled construction of the corpus. Place coordinates use data from OpenStreetMap, © OpenStreetMap contributors, available under the Open Database License.

# DISCLAIMERS

The system organizes attributed news reporting. It does not establish that a reported accident occurred, verify legal fault, or replace official crash investigation. Any operational use should include qualified human review, privacy safeguards, local legal review, and source-specific terms-of-use compliance.

**REFERENCES**

@@REFERENCES@@
