# Ideas

## General

Rather than identifying which bees are in or out of a festoon, what if we could instead use label-free groupings of predicted behavior probabilities?

## May 2026 Hackathon Alignment

Bryan Daniels' current major goal is to ask whether the transition to comb-building in honey bees is a collective transition with hysteresis.

Open analysis goals from the May 2026 planning note:

1. Identify bees with comb-building-relevant behavior in tracking data, including stationary bees in hanging festoon structures and possible related behaviors such as washboarding or moving around the festoon area.
2. Validate that inferred festooning-like behaviors actually correspond to festooning by matching tracking-data time frames to video.
3. Determine features that predict whether a bee will join a festoon, such as age and past task history.
4. List candidate features and mechanisms to test.
5. Describe which bees build comb, when they do it, and for how long.
6. Use predictive features to build a computational model of comb-building.
7. Analyze that computational model to locate and characterize collective transitions.

Working constraints and context:

- The days with festoons in the 2019 data are roughly days 4-20 and 46-65.
- Preliminary notebook results suggest bees in the new-comb area tend to be older, stays in the new-comb/festoon area are typically under an hour, and young bees move more slowly.
- The preparation reading is Delaplane, "Emergent Properties in the Honey Bee Superorganism," especially pages 10-13 on initiation of comb construction and cell construction.

## References for a Label-Free Collective-Control Path

A reasonable first step is to infer label-free, probabilistic behavioral states for each bee over time, then ask whether aggregate state probabilities and transition rates reveal collective-control coordinates for comb-building.

Work should stay compatible with the repo's current sklearn/numpy/pandas style. Initial models can use feature windows, PCA, Gaussian mixture models, Bayesian Gaussian mixtures, and related probabilistic clustering/state summaries before considering heavier behavior-analysis packages.

Useful references:

- Daniels and Lynch, "Design patterns in the tuning of collective transitions" (`daniels1DesignPatterns`, preprint in Zotero). Frames the biological question as collective behavior moving relative to transition manifolds. Important for follow-on questions: aggregate state occupancy, transition rates, hysteresis-like paths, sensitivity, and low-dimensional control variables.
- Smith, Davidson, Wild, Dormagen, Landgraf, and Couzin (2021 preprint; 2022 iScience), "The dominant axes of lifetime behavioral variation in honey bees" / "Behavioral variation across the days and lives of honey bees," doi:10.1101/2021.04.15.440020 and doi:10.1016/j.isci.2022.104842. Directly relevant data foundation: thousands of honey bees tracked at 3 Hz across an entire summer, behavioral metrics across timescales, individual variation, and transitions through behavioral space toward foraging. Especially important caution: PCA and hierarchical clustering revealed dominant continuous axes of variation, but the clusters were used descriptively rather than as evidence for sharply separated behavioral roles.
- Wild et al. (2021), "Social networks predict the life and death of honey bees," Nature Communications, doi:10.1038/s41467-021-21212-5. Introduces "network age," a low-dimensional behavioral/social descriptor inferred from interaction networks. It predicts task allocation, future behavior, activity patterns, and survival better than chronological age in several analyses. Useful next-step precedent: build network or interaction-derived coordinates from proximity/contact/trophallaxis-like features, then compare them with movement-only behavioral states and age/festoon annotations.
- Daniels, Wang, Page, and Amdam (2023), "Identifying a developmental transition in honey bees using gene expression data," PLOS Computational Biology, doi:10.1371/journal.pcbi.1010704. Useful conceptual bridge from bee biology to transition inference: bistability, PCA-like low-dimensional projections, Gaussian/model-comparison baselines, and age-related behavioral transition.
- Wiltschko et al. (2015), "Mapping Sub-Second Structure in Mouse Behavior," Neuron, doi:10.1016/j.neuron.2015.11.031. Classic label-free behavioral-module reference: behavior as reused modules with transition probabilities. The data modality differs, but the idea of probabilistic state sequences and transition structure is directly relevant.
- Hsu and Yttri (2021), "B-SOiD, an open-source unsupervised algorithm for identification and fast prediction of behaviors," Nature Communications, doi:10.1038/s41467-021-25420-x. Useful as a modern computational-ethology precedent for clustering movement-derived features and then training fast classifiers. Treat as conceptual inspiration, not a dependency target.
- Weinreb et al. (2024), "Keypoint-MoSeq: parsing behavior by linking point tracking to pose dynamics," Nature Methods, doi:10.1038/s41592-024-02318-2. Current reference for unsupervised behavioral syllables from keypoint dynamics. More sophisticated than needed for the first pass, but important for framing label-free behavior states.
- Luxem et al. (2022), "Identifying behavioral structure from deep variational embeddings of animal motion," Communications Biology, doi:10.1038/s42003-022-04080-7. Shows unsupervised probabilistic behavior segmentation with latent states and HMM-style motif inference. Useful precedent for state probabilities and motif communities, though probably too heavy for the first sklearn pass.
- McKenzie-Smith, Wolf, Ayroles, and Shaevitz (2025), "Capturing continuous, long timescale behavioral changes in Drosophila melanogaster postural data," PLOS Computational Biology, doi:10.1371/journal.pcbi.1012753. Insect precedent for high-resolution pose/postural tracking over multi-day timescales, unsupervised behavioral classification, and daily/lifetime changes in behavioral composition.
- Blanc et al. (2025), "Statistical signature of subtle behavioral changes in large-scale assays," PLOS Computational Biology, doi:10.1371/journal.pcbi.1012990. Drosophila larva precedent for learning a continuous latent behavioral representation, then comparing genotype-level behavior as distributions in that latent space.
- Tunstrøm et al. (2013), "Collective states, multistability and transitional behavior in schooling fish," PLOS Computational Biology, doi:10.1371/journal.pcbi.1002915. Useful collective-behavior analogue for detecting aggregate states, multistability, and transitions from trajectory data.
- Boettiger and Hastings (2012), "Quantifying limits to detection of early warning for critical transitions," Journal of the Royal Society Interface, doi:10.1098/rsif.2012.0125. Useful caution for follow-on transition diagnostics: early-warning signals can be difficult to detect reliably and need careful controls.
- McLachlan and Peel (2000), "Finite Mixture Models," Wiley, doi:10.1002/0471721182. General statistical reference for mixture models, posterior component probabilities, and model-selection/interpretation issues behind Gaussian mixture baselines.
- Aitchison (1982), "The Statistical Analysis of Compositional Data," Journal of the Royal Statistical Society Series B, doi:10.1111/j.2517-6161.1982.tb01195.x. Useful once per-state probabilities are aggregated, because state occupancy vectors are proportions constrained to sum to one.

Immediate modeling implication:

1. Fit label-free states using movement/context features only, holding out age and festoon/new-comb annotations for interpretation.
   References: Smith et al. (2021/2022) for movement/substrate axes in honey bees; Wiltschko et al. (2015), Hsu and Yttri (2021), Luxem et al. (2022), and Weinreb et al. (2024) for label-free behavior-state discovery from movement; McKenzie-Smith et al. (2025) and Blanc et al. (2025) for insect-specific latent/postural behavior precedents.
2. Save full per-state probabilities, not just hard labels.
   References: McLachlan and Peel (2000) for mixture-model posterior memberships; Wiltschko et al. (2015) and Luxem et al. (2022) for probabilistic state sequences and transition/motif structure in computational ethology.
3. Treat fitted clusters as probabilistic summaries of continuous behavioral variation unless there is strong evidence for discrete roles.
   References: Smith et al. (2021/2022) for continuous dominant axes and descriptive clustering in honey bees; McKenzie-Smith et al. (2025) for continuous multi-timescale insect behavior; Blanc et al. (2025) for distributions in a learned latent behavior space.
4. Aggregate probabilities over bees and space to construct candidate collective coordinates.
   References: Daniels and Lynch (preprint) for low-dimensional collective-control coordinates; Tunstrøm et al. (2013) for aggregate collective states and multistability from trajectory data; Aitchison (1982) for treating aggregated state occupancies as compositional data.
5. Test whether those coordinates change, become multistable, or show transition-like dynamics during days 4-20 and 46-65.
   References: Daniels and Lynch (preprint) for transition manifolds/design patterns; Daniels et al. (2023) for transition inference in honey bee development; Tunstrøm et al. (2013) for multistable collective states; Boettiger and Hastings (2012) for caution around early-warning diagnostics.
6. Keep network-age-style interaction embeddings as a second chunk after the movement/substrate feature baseline is reproducible.
   References: Wild et al. (2021) for network age, social-interaction embeddings, and prediction of task allocation/survival; Smith et al. (2021/2022) for comparing those interaction-derived coordinates against movement/substrate behavioral axes.

Hackathon-sized implementation path:

1. Build a time-window feature table for each bee, with movement features, spatial context, day/time, and a persistent identifier linking each row back to video time.
   Maps to goals: behavior identification, video validation, descriptive analysis.
2. Fit a small set of reproducible sklearn baselines: PCA plus Gaussian mixture models/Bayesian Gaussian mixture models, saving component probabilities for every bee-window.
   Maps to goals: label-free behavior summaries and probabilities for downstream prediction.
3. Create validation panels for selected high-probability states during known festoon days, prioritizing days 4-20 and 46-65 and rows that can be matched to video.
   Maps to goals: validate whether inferred festooning-like states correspond to visible festooning.
4. Model festoon-joining or high-festoon-probability entry as a prediction problem using age, recent state probabilities, past task/state history, local density, and spatial context.
   Maps to goals: identify predictive features and candidate mechanisms.
5. Aggregate state probabilities over bees, space, and time to produce candidate collective coordinates, then compare approach and retreat trajectories across the two 2019 festoon periods.
   Maps to goals: test for collective-transition and hysteresis-like signatures.
6. Use the predictive model as the first computational model of comb-building, then test whether changing candidate control variables shifts the inferred collective coordinate.
   Maps to goals: build a computational model and analyze it for collective transitions.
