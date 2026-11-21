# DEVLADLOG AI #16 — Machine learning fundamentals: can you believe your model's number?

Blog guide: [Machine Learning Fundamentals: The Complete Guide (2025)](https://www.devladlog.com/articles/ai/2025-01-02-machine-learning-fundamentals-complete-guide-2025/)

Episodes 1 to 15 were about language models. Not every question at the Contoso Porto service desk needs one. "Will this
ticket breach its SLA?" is a classic table problem, and the point of this episode is the part of ML that decides whether a
score can be believed: **a baseline with no skill, leakage, imbalance, how you split, overfitting, and a threshold taken from
costs.** It trains real scikit-learn models on a synthetic, fixed-seed table with the pitfalls planted on purpose, so every
pitfall is detectable by a test. Episode 8 covers drift after go-live and episode 14 covers pipelines and tracking: this one stops
at "is the number honest, and what does the model card say".

| Pitfall (planted in `data.py`) | How the episode shows it | Where |
|---|---|---|
| Rare positives (13 % of tickets breach) | A model that always says "no breach" is 87 % accurate; the baseline table compares accuracy with AUC and average precision | `audit`, `baseline` |
| A column from the future (`first_response_minutes`, known only after pickup) | Single-column AUC scan + "not available at arrival" list; exit code 1 | `audit` |
| Repeat requesters (a personal propensity per employee) | Random split shares people between train and test; group split does not | `compare` |
| Time (180 days) | Time split: oldest days train, newest test | `compare` |
| Overfitting | A decision tree's train and validation average precision per `max_depth` | `depth` |
| A default threshold of 0.5 | Threshold from the cost of a miss (10) versus a false alarm (1), chosen on out-of-fold predictions | `train` |
| Nothing to ship | Model card JSON, a scorer that refuses fields not known at arrival, a verdict against "flag nothing" and "flag everything" | `train`, `score` |

| Path | What it is |
|---|---|
| [`src/mlbasics/data.py`](src/mlbasics/data.py) | The synthetic table (8,000 tickets, 500 requesters, 180 days), the column lists, a data fingerprint |
| [`src/mlbasics/audit.py`](src/mlbasics/audit.py) | Class balance, missing values, repeat requesters, leakage scan (single-column AUC and "available at arrival") |
| [`src/mlbasics/splits.py`](src/mlbasics/splits.py) | Random (stratified), group (whole requesters) and time splits, `overlap()` |
| [`src/mlbasics/model.py`](src/mlbasics/model.py) | One `Pipeline` per model (imputer, scaler, one-hot, estimator): logistic regression, random forest, decision tree, a no-skill dummy |
| [`src/mlbasics/evaluate.py`](src/mlbasics/evaluate.py) | AUC, average precision, Brier, confusion, cost, threshold from costs |
| [`src/mlbasics/experiments.py`](src/mlbasics/experiments.py) | `compare_protocols`, `baseline`, `depth_curve`, grouped-CV `select_model`, `train_and_test`, `verdict` |
| [`src/mlbasics/card.py`](src/mlbasics/card.py), [`report.py`](src/mlbasics/report.py), [`cli.py`](src/mlbasics/cli.py) | Model card + scorer, terminal tables, `python -m mlbasics data / audit / baseline / compare / depth / train / score` |
| [`tests/`](tests) | 43 pytest tests |

Tested with Python 3.13, `scikit-learn 1.9.1`, `numpy 2.5.5`, `pandas 3.1.1`, `joblib 1.6.0`. No Azure, no network after `pip install`.

## Run it (no Azure needed)

```bash
python -m venv .venv && . .venv/bin/activate
pip install -r requirements.txt
python -m pytest tests -q                       # 43 passed (about 25 s on 2 shared CPUs)
export PYTHONPATH=src
python -m mlbasics audit ; echo exit=$?         # 1: first_response_minutes is not known when the ticket arrives
python -m mlbasics audit --drop first_response_minutes ; echo exit=$?    # 0
python -m mlbasics baseline
python -m mlbasics compare                      # about 10 s
python -m mlbasics depth
python -m mlbasics train --out build ; echo exit=$?     # 0 = beats both do-nothing policies; 1 = do not ship
python -m mlbasics score ticket.json            # risk for one new ticket; refuses first_response_minutes
```

Real output on this machine (the recording prints its own; deterministic seeds, but BLAS and library versions can move the
last digit):

```
$ python -m mlbasics audit
rows 8,000   positives 1,036 (13.0%)   always-predict-no accuracy 87.1%
first_response_minutes       0.979  SUSPECT: not known when the ticket arrives     (next best column: 0.637)

$ python -m mlbasics baseline
model                       accuracy     AUC      AP   Brier
always the prior (no skill)     0.868   0.500   0.132   0.115
logistic regression             0.870   0.713   0.306   0.105

$ python -m mlbasics compare
evaluation                  test rows shared people prevalence   logistic AP  logistic AUC     forest AP    forest AUC
random + leaky column           2,000           492      13.0%         0.964         0.985         0.946         0.975
random + requester id           2,000           492      13.0%         0.397         0.755         0.352         0.761
group split (new people)        1,976             0      13.2%         0.305         0.712         0.332         0.744
group split, no id              1,976             0      13.2%         0.306         0.713         0.314         0.737
time split (later days)         2,001           492      13.3%         0.315         0.727         0.324         0.738

$ python -m mlbasics depth        (train AP / validation AP)
  1: 0.189/0.184   3: 0.280/0.243   5: 0.394/0.262   8: 0.527/0.229   12: 0.663/0.208   none: 1.000/0.153

$ python -m mlbasics train
chosen: forest {'min_samples_leaf': 5}     threshold 0.101
test once: 1,976 tickets from 125 requesters never seen in training
  AUC 0.737   average precision 0.314 (prevalence 0.132)   Brier 0.104
  caught 206 of 261 breaches (recall 79%), 722 false alarms (precision 22%)
  cost: model 1272   flag nothing 2610   flag everything 1715
RESULT: ship candidate
```

How to read it: the leaky column turns a model with real but modest skill (AUC about 0.74) into a "0.96 average precision" one; sharing
requesters between train and test adds about 0.09 average precision on top of the honest figure; the unconstrained tree scores 1.000
on its own training tickets and falls to 0.153 on unseen requesters. "Ship candidate" is deliberately modest: at the cost ratio chosen
the model flags about half of all tickets to catch 79 % of breaches, which beats the two do-nothing policies on cost but is only worth
shipping if a dispatcher really values a miss at ten false alarms.

What the tests cover (real scikit-learn models on the synthetic table; they prove the pitfalls exist in the data and that the tools detect them):
- `test_data_audit_splits.py`: data is deterministic and seed-dependent, fictional values only, the leaky column has AUC above 0.95, the scan flags that column and nothing else,
  a copy of the target is flagged, random split shares hundreds of requesters, group split shares none, time split only looks forward.
- `test_model_evaluate.py`: the scaler's mean is the training mean, unseen categories don't crash, the dummy scores the prevalence, the accuracy paradox, threshold moves down when a miss costs more.
- `test_experiments.py`: leaky average precision above 0.9 versus honest below 0.5; shared requesters inflate the score; deep trees memorise (train 1.0, validation far lower, best depth neither 1 nor unlimited);
  the trained model beats both do-nothing policies; the verdict explains failures.
- `test_card_cli.py`: the model card, the scorer (refuses leaky and incomplete tickets, accepts an unseen category), every command and its exit code (0 / 1 / 2).

## What we learned / gotchas

- **An abnormally good score is a symptom.** Learn (Automated ML, "Prevent target leakage"): target leakage means the model gets data it will not have at prediction
  time, it is often visible as abnormally high accuracy, and it can hide from a train/test comparison. The forecasting FAQ adds that a perfect validation score usually means leakage.
  Our scan uses two independent warnings: not available at arrival, and a single column that almost copies the answer.
- **Accuracy flatters rare positives.** Learn: imbalance "can lead to a falsely perceived positive effect of a model's accuracy", and for imbalanced data it recommends looking at the confusion
  matrix, precision-recall and ROC rather than accuracy alone. Here the no-skill model has the same accuracy as the real one to within two points. Average precision has a floor of the prevalence, so 0.132 is "no skill" and 0.306 is real.
- **Splits answer different questions.** Random rows are only valid if rows are independent; here an employee's tickets are not. The group split matches "a new employee writes in tomorrow", the time
  split matches "the model is used on later days". Pick the one that matches how the model is used, and say which in the model card.
- **Identifiers are not features.** `requester_id` helps a random-split score (0.397 versus 0.305 average precision for logistic regression) and is useless for new people, so the final model excludes it.
- **Overfitting is a gap, not a number.** Learn: test accuracy should always be lower than training accuracy; what matters is how much lower. Complexity limits (tree depth) and cross-validation are the standard remedies;
  `depth` shows the training score going up while the unseen score peaks at depth 5 and then falls.
- **Fit preprocessing inside the pipeline.** `Pipeline` + `ColumnTransformer` make imputation, scaling and encoding learn from the training rows of each fold only. A test checks that the scaler's mean is the training mean.
- **Cross-validate on groups.** `GroupKFold` keeps every employee on one side of each fold. Plain k-fold would leak identity into model selection. For reference, Learn says Automated ML defaults to three-fold cross-validation for
  1,000 to 20,000 rows when no validation data is given; we use five grouped folds on 6,024 training rows.
- **The threshold is a business decision.** 0.5 is a default, not a rule. The cost ratio (10 : 1) is an assumption made up for the demo; the service desk manager owns it. The threshold is chosen on out-of-fold predictions of the
  training rows, never on the test set, and the test set is used once.
- **One split is one draw.** With 125 test employees, another seed moves every number. I saw this directly: an earlier version of the recipe had weaker observable effects (AUC about 0.64) and the single-split test score was well
  below the cross-validated one. I then strengthened the observable effects so the demo model has real skill; the requester effect and the leaky column are unchanged. Treat small differences between models as noise.
- **Synthetic data proves the method, not the business result.** The numbers say nothing about real Contoso tickets. The model card says so (`not_for`), and the next step in a real project is the same audit on a few months of anonymised tickets.
- **Not covered:** calibration curves, class weights or resampling, feature importance and fairness checks (episode 6 covers responsible AI), drift (episode 8), tracking and registries (episode 14).

## References

- [Prevent overfitting and imbalanced data with Automated ML](https://learn.microsoft.com/azure/machine-learning/concept-manage-ml-pitfalls) — overfitting, target leakage, imbalanced data, cross-validation
- [Evaluate automated machine learning experiment results](https://learn.microsoft.com/azure/machine-learning/how-to-understand-automated-ml) — choosing classification metrics (ROC AUC, average precision, confusion matrix for imbalanced data)
- [Frequently asked questions about forecasting in AutoML](https://learn.microsoft.com/azure/machine-learning/how-to-automl-forecasting-faq) — leakage and perfect validation scores
- [Set up AutoML training for tabular data](https://learn.microsoft.com/azure/machine-learning/how-to-configure-auto-train) — default validation technique by data size
- [Cross Validate Model component](https://learn.microsoft.com/azure/machine-learning/component-reference/cross-validate-model) — how cross-validation works and its advantages
- Blog: [Machine Learning Fundamentals: The Complete Guide (2025)](https://www.devladlog.com/articles/ai/2025-01-02-machine-learning-fundamentals-complete-guide-2025/)
