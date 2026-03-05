# Agency: updated specification
*21 February 2026*

---

## What Agency is

### The name

"Agency" carries two meanings, both intentional. The first is partial autonomy — the capacity to act independently within defined limits. The second is the organisational form: a staffing agency, which holds a pool of people with different capabilities and deploys them against work that clients bring. A machine agency works the same way.

"Agent" also carries two meanings: an entity that acts autonomously, and an entity that acts on behalf of someone else. Agents in Agency are the second kind. They act on behalf of the human who commissions them. This is the foundational structure of principal-agent theory: the agent acts under delegated authority, while the principal retains ultimate authority over the fitness function (Jensen & Meckling, 1976; Eisenhardt, 1989). Their autonomy is real but bounded — bounded by the trade-off configurations the human has set.

### The two-part mission

Agency has two founding purposes, not one.

**First: port organisational wisdom to machine organisations.** Centuries of hard-won understanding of how to get good work from agents — role decomposition, explicit trade-off specification, performance evaluation, controlled evolution, selection pressure — applied to machine agents. The structural problems are the same whether agents are human or machine: how do you specify what you want, evaluate whether you got it, and improve the system over time.

**Second: systematically explore what becomes newly possible in machine organisations.** Not just porting what works for humans, but actively investigating what works better when agents are tireless, consistent, scalable, and perfectly instruction-following within fully specifiable rules. Human organisational design is constrained by human limitations. Machine organisations aren't constrained in the same ways. The most significant unexplored territory is novel role components: capabilities that didn't make sense for human organisations but become viable or newly powerful when executed by machines (Tan, 2015, p. 120).

### Relationship to meaningmaking

Agency is grounded in a distinction between meaningmaking work — making subjective decisions about the relative value of things, which only humans can do (Tan, 2023)[^1] — and non-meaningmaking work, which machines can do better than humans in three areas: data management (storage, search, retrieval) for already-explicated data; data analysis (pattern-finding) where patterns are pre-established as meaningful by humans or surfaced for human interpretation; and rule-following where rules are fully specifiable and fully specified (Tan, 2024b)[^3].

There are at least four distinct types of meaningmaking, all of which are uniquely human: deciding that something is subjectively good or bad; deciding it is subjectively worth doing; deciding value-orderings and degrees of commensuration among a set of things; and deciding to reject existing decisions about subjective value (Tan, 2024a)[^2].

**Humans retain all meaningmaking in Agency.** Every subjective decision — what objectives are worth pursuing, what trade-offs are acceptable, what "better performance" means — is made by the human commissioning the agency. Agency never attempts to take over these decisions.

**Agents do the non-meaningmaking work.** Role components are capabilities for the three areas where machines currently outperform humans. The more fully specifiable a role component's task, the more powerful the machine agent executing it.

**Trade-off configurations are crystallised meaningmaking.** The human specifies acceptable and unacceptable trade-offs in advance — doing the meaningmaking work before execution (Tan, 2024a)[^2]. The agent then operates within the space that meaningmaking has defined, without needing to make any subjective value decisions during execution.

**Front-loaded meaningmaking** is the key to high-functioning human-machine organisations. If a human does the meaningmaking work thoroughly enough in advance — specifying objectives, trade-off configurations, evaluation rubrics, completion criteria — what remains for the agent to execute may contain so little residual subjective judgment that the agent can perform it effectively. This isn't agents doing meaningmaking. It's humans front-loading meaningmaking completely enough that none remains during execution. The Boris methodology — which forces explicit articulation of trade-offs people hold but haven't stated — is the practical tool for this front-loading work (Tan, n.d.)[^4].

### What Agency is not

Agency is not about modifying how tasks are configured in a task management system (though see section below about *task creator* agent-types). It is about understanding how agents can be reconfigured and recomposed — developing the collection of agents that a machine organisation uses to do work. Agency is designed to work with any task management system, not just Workgraph.

---

## Conceptual primitives

Agency stores three types of primitives separately:

- **Role components** — individual capabilities: the ability to do a specific thing
- **Desired outcomes** — specifications of what success looks like for a particular type of work
- **Trade-off configurations** — sets of acceptable and unacceptable trade-offs governing how work is done

These are stored as independent, uncommitted objects. The conceptual relationship between these primitives is:

![Conceptual relationship between primitives](<Pasted image 20260222080808.png>)

Pre-composed agents — particular combinations of role components + desired outcomes + trade-off configurations — exist as a cache on top of the primitive store, not as the ground truth. The primitive store is the ground truth.

The architecture directly grounds in Tan (2015, p. 112), which shows that stable roles in groups operating under uncertainty are built up as modular assemblages of validated capabilities: individual role components proposed, tested, and integrated one at a time, with the stable role emerging from accumulation rather than being defined in full in advance. Role-assembly theory in organisational research similarly proposes that jobs are put together from multiple task components rather than being selected as monolithic wholes (Cohen, 2012).

> **[Challenge to current implementation]**: The current implementation holds pre-composed Identities — fully assembled agents that bundle role components (skills), desired outcomes, and trade-off configurations (Objectives) in a single object. This conflates the primitive store with the composition cache. The primitive store architecture this spec requires does not yet exist as a separate construct. Separating primitives from compositions is the key architectural change.

This matters for evolution: the *evolver* operates on primitives and their combinations. A pool of pre-built agents can only recombine at the agent level. A primitive store can recombine at any level.

---

## Role components

### What a role component is

A role component is the ability to do a specific thing, separated from what that ability is pointed at. It is purely a capability — not a bundled mix of capability, persona, and target outcome. The term and concept derive from Tan (2015, p. 112), which shows that in groups operating under genuine uncertainty, stable roles are effectively constructed by assembling validated capabilities into configurations that satisfy both the person performing them and the organisation relying on them. This allows roles to be emergent and adaptive as the environments in which they operate change.

Current AI skills typically bundle three conceptually distinct things: a perspective or lens (how to interpret information), a procedural capability (how to produce something), and a target outcome (what to produce and for whom). This bundling prevents meaningful evolution: you cannot isolate what is working from what is not, and you cannot recombine parts across agents without dragging the whole bundle along.

A directly parallel problem appears in the multitask principal-agent framework (Holmstrom & Milgrom, 1991): when a single agent performs multiple tasks under a bundled incentive scheme, it becomes impossible to accurately attribute performance to specific tasks or optimise incentives for each independently.

> **[Challenge to current theoretical grounding]**: The current theoretical grounding cites Holmstrom & Milgrom (1991) as grounding for the bundled Role struct combining skills and desired_outcome. This spec reads H&M differently: H&M's core finding is that bundling generates distorted effort allocation — which supports the case for separating role components from desired outcomes rather than bundling them.

> **[Rejects standard selection approach]**: Standard selection theory assumes predefined, stable roles and optimises for fit between aspirant and role (Jovanovic, 1979; Stewart & Carson, 1997; Schmidt & Hunter, 1998). Negotiated joining, by contrast, treats roles as emergent and open-ended, constructed through iterative proposition, trial, evaluation, and integration of role components. The machine-organisation analogue is a primitive store of role components that can be combined into novel agent configurations, rather than a fixed set of predefined agent types against which new agents are selected.

Role components should be specified at the granularity where they are:

1. **Independently testable** — you can ask whether this component performs well or poorly, holding others constant. This mirrors negotiated joining's trial subprocess (Tan, 2015, pp. 115–116): proposed role components are tested individually through practical work interactions, with each trial evaluated before the component is integrated.
2. **Meaningfully recombinable** — combining two role components produces something coherent.
3. **Single-typed** — each component is purely capability, not capability-plus-aim mixed together.

**Example decomposition**: A bundled skill described as "experienced geostrategic analyst writing a robust report for senior decision-makers in a for-profit company" actually contains: a role component of geostrategic framework familiarity, a role component of report writing, and a desired outcome of producing a report for senior decision-makers in a for-profit context. Separating these allows the role components to be recombined with different desired outcomes.

### Three categories of role components

**Translated human skills** — capabilities that exist in human organisations, ported to machine agents. Examples include: Geostrategic analysis, code review, report writing, brainstorming for viability, brainstorming for wackiness.

**Enhanced human skills** — capabilities humans have but machines can execute better in specific dimensions: tireless repetition without degradation, perfect instruction-following when instructions are fully specifiable, no corner-cutting when explicitly prohibited, parallel execution at scale, rigorous consistency. These are the capabilities where human biases, inconsistency, and fatigue create systematic disadvantages relative to machines (Tan, 2024b, "Human failings and AI capabilities")[^3].

**Novel role components** — capabilities that didn't make sense for human organisations (humans couldn't execute them reliably or cheaply enough) but become viable or newly powerful when done by machines. Examples: systematic adversarial testing of every assumption in a document, exhaustive enumeration of edge cases, continuous monitoring of a parameter space.

Tan (2015, p. 120) identifies the human analogue: the most disruptive capability additions to organisations operating under genuine uncertainty — those that fundamentally change how the organisation works, not just how it executes specific tasks — come disproportionately from people whose prior experience is in domains distant from the organisation's existing work. Novel machine role components are the *agent creator*'s primary search target. They are also the most durable source of competitive advantage: the causal ambiguity that surrounds how an organisation developed a particular capability makes it difficult for competitors to replicate even when they can observe the outcome (Lippman & Rumelt, 1982; Barney, 1991).

---

## Desired outcomes

A desired outcome specifies what success looks like when a particular combination of role components is applied to a task. It is the target the role is pointed at — what the agent is aiming to produce.

Desired outcomes are separate from role components. The same role components can be pointed at different desired outcomes, producing meaningfully different agents. Tan (2015, p. 112) makes this point in the organisational context: the same role components, directed at different targets, produce roles that are novel in configuration even when the underlying capabilities are familiar. The formal grounding is in Holmstrom & Milgrom (1991): when capabilities and targets are bundled into a single performance object, effort cannot be optimised across multiple incompatible objectives; separating them allows each dimension to be specified and evolved independently.

---

## Trade-off configurations

### What a trade-off configuration is

A trade-off configuration specifies how an agent should navigate competing considerations when pursuing an objective. It consists of:

- **Acceptable trade-offs**: what the agent is permitted to sacrifice. "It is acceptable for this to take a long time." "It is acceptable to use many tokens."
- **Unacceptable trade-offs**: hard constraints on what cannot be sacrificed. "Reliability cannot be traded away." "Accuracy is non-negotiable."

Trade-off configurations can be specified at any level of detail — from highly detailed specifications covering every foreseeable trade-off to high-level statements that leave significant latitude to the agent. Greater specification precision reduces residual meaningmaking in execution; lower specification precision leaves more subjective judgment for the agent to exercise (which it cannot do well, since agents cannot do meaningmaking).

The practical limits of full specification are well-established: Hart & Moore (1988) show that real-world contracts are always incomplete because not all contingencies can be anticipated in advance; Hayek (1945) identifies the deeper problem that the knowledge required for full specification is inherently dispersed and often tacit. These constraints make front-loaded meaningmaking by humans not merely preferable but structurally necessary.

### Relationship to objectives

A trade-off configuration is not the same as an objective. An objective specifies what the agent is trying to achieve. A trade-off configuration clarifies the objective by resolving the ambiguities that any real objective contains. The objective "write a piece of code that passes a set of tests" is underspecified. Adding a trade-off configuration — "do it as fast as possible; token cost is irrelevant" versus "make it as compact as possible; time taken is irrelevant" — makes the objective operationally meaningful.

This means trade-off configurations and objectives can evolve independently. Objectives (what is worth pursuing) are meaningmaking decisions (Tan, 2023, 2024a)[^1][^2] that require human oversight when they change. Trade-off configurations (how to pursue an objective) can be evolved more automatically, because they operate within the space the objective's meaningmaking has already bounded.

> **[Challenge to current implementation]**: The current implementation's "Objective" struct conflates objective and trade-off configuration, treating both as evolvable parameters under the ObjectiveTuning strategy. This spec argues that objectives — what is worth pursuing — are meaningmaking decisions that must not be evolved without human oversight. Evolving objectives automatically is not equivalent to evolving trade-off configurations: the former changes what the agent is trying to achieve (a subjective value decision only humans can make); the latter changes how the agent pursues an already-established aim (which can be evolved more automatically within the bounds the human's meaningmaking has set). See also the GEPA section under The evolver.

### The Boris connection

The idea that trade-off configurations are inherently subjective and profoundly condition action is the basis of Boris, a trade-off articulation process developed around 2012 and deployed in organisations ranging from private equity firms to multilateral institutions (Tan, n.d.)[^4]. Boris forces stakeholders to make explicit what desirable outcomes they are willing to sacrifice and what is non-negotiable — precisely the information a trade-off configuration encodes. A trade-off configuration in Agency is, in effect, a Boris-style specification for a machine agent.

### Standard and custom configurations

Standard trade-off configurations — "do it fast, cost is irrelevant"; "do it well, time is irrelevant"; "minimise token use" — are likely defaults available in most deployments. But humans can specify any trade-off configuration they want, including domain-scoped configurations ("only search within capabilities relevant to Asian equities research") or configurations that govern the shape of search rather than just its intensity.

---

## Agents and actor-agents

**An agent** is a role (combination of role components + desired outcomes) paired with a trade-off configuration. This is the deployable unit — a specific configuration of "what I can do and what I'm aiming for" combined with "what trade-offs I'm willing to make." Agents can exist in the agency without being assigned to any task; these pre-composed agents live in a cache which identifies the primitives from which they are composed, as well as the tasks and clients to which they have been formerly deployed and the evaluations they received on those tasks. Primitives can inherit evaluations from the agents they were elements of.

**An actor-agent** is an agent that has been assigned to a specific task and is actively performing it. The terminological distinction matters both functionally and for clarity: the agency maintains a population of agent configurations (pre-composed in the cache), but only some are active at any given time.

---

## The agency as a system

### Primitive store and composition cache

The agency stores primitives (role components, desired outcomes, trade-off configurations) as independent indexed objects with rich metadata (some of these metadata include: 1. former agents they have been elements of, 2. former actor-agents they have been elements of, 3. evaluations of agents they have formerly been elements of). Pre-composed agents are a cache on top of this store — combinations that have been assembled, tested, and found to be at least serviceable. The cache reduces *assigner* workload and guarantees a floor of acceptable quality on demand.

The cache is populated by: conventional combinations (attractor areas where certain primitives tend to go together), high-performing compositions discovered through learning runs, and explicitly human-authored agents. Cache entries are popular configurations, not all possible configurations. The primitive store is the ground truth; the cache is a performance optimisation.

**Attractor areas** represent accumulated knowledge about what combinations tend to work. They are probability weights, not hard constraints. Nelson & Winter (1982) describe an analogous phenomenon in human organisations: organisational routines function as stable attractors that encode accumulated knowledge about effective practices. Attractor areas in Agency are the machine-organisation equivalent: probability weights over primitive combinations, encoding knowledge about what tends to perform well.

### Two deployment models

**Outsourced agency** — the hiring organisation comes to Agency on demand, uses whatever agent configurations Agency has developed, pays per deployment. No investment in building the stable. No proprietary accumulation. Flexible and low-commitment, but the organisation never develops capabilities competitors cannot also access.

**In-house agency** — the organisation runs its own Agency instance. It pays for learning runs, evolution, agent creation. Over time it accumulates a proprietary stable of primitives and composed agents that reflect its specific work, trade-off preferences, and performance history. Competitive advantage develops through causal ambiguity (Lippman & Rumelt, 1982): competitors cannot easily replicate what the stable has become because they cannot fully observe what combination of investments, learning runs, and evolutionary paths produced it, nor can they observe the primitives from which the agents are composed. From the resource-based view (Barney, 1991), a proprietary primitive store that is valuable, rare, inimitable, and non-substitutable — properties that follow from its unique developmental history — generates durable competitive advantage.

### Federation as an option, not as a default

Roles, desired outcomes, and trade-off configurations can be shared across projects or organisations. Federation is optional and context-dependent — it makes sense within holding companies where sharing primitives is desirable, but works against proprietary accumulation for in-house agencies. Each primitive carries access control metadata: owner and access policy (private, shared, or open). Sharing is a deliberate strategic choice, equivalent to the decision a human organisation makes when deciding whether to publish research or share supplier relationships.

### Run modes

The agency can be operated across a continuum between two poles:

**Performance mode** — an *assigner* actor-agent searches the composition cache first and deploys the fastest acceptable match. Smart matching, no randomisation. Used when output quality is known to be sufficient and delivery speed matters.

**Learning mode** — an *assigner* actor-agent deliberately composes from primitives, including non-conventional combinations, to generate performance data and potentially populate the cache with new high-performers. Structured randomisation with things held constant, enabling retrospective inference about which primitives contribute to performance. Used on-demand, where time and other resources are available to large experiments on agent composition and agent configuration (i.e., configurations of actor-agents)

Calibrating where on this continuum to operate is directly analogous to the exploration-exploitation tradeoff (March, 1991): exploitation of known-good configurations produces reliable, near-term returns; exploration of novel configurations generates variance and may produce superior long-run performance, at the cost of near-term certainty. March (1991) shows that adaptive systems systematically underinvest in exploration because exploitation returns are more certain and more immediate. Explicit learning mode is the mechanism for counteracting this drift; without it, Agency will tend to converge on a fixed set of attractor-area compositions.

> **[Response to known structural tendency in current theoretical grounding]**: The current theoretical grounding identifies exploration underproduction (March, 1991) as a known structural tendency. The performance/learning mode continuum directly addresses this: learning mode creates structured incentives for exploration that counteract the natural drift toward exploitation.

**Two levels of reward signal** are needed:
- **Task-level** — how well did this agent complete this task
- **Organisational-level** — how did this configuration of agents working together contribute to overall machine organisation performance

These can diverge. An agent that performs well on its individual task but creates coordination overhead, blocks other agents, or produces outputs that are hard for downstream agents to use is a poor organisational fit even if its task-level scores are high. Holmstrom & Milgrom (1991) make the parallel point for human organisations: rewarding individual task performance without accounting for multi-task interactions distorts overall performance.

> **[Gap in current implementation]**: The current theoretical grounding identifies the two-level reward signal as a gap in the current implementation. This spec fills that gap explicitly, treating the two levels as complementary and non-substitutable.

---

## Well-formed tasks

Task specification is not part of Agency, but is relevant to the work that Agency does. A well-formed task specifies three things:

**1. What the task is** — in as much detail as possible. These can be process instructions (including sources of data), relevant prior art directions, and can be specified in as much or as little natural language detail as the user (or its task development agent) provide. In principle, the more detail provided, the easier it will be for an *assigner* actor-agent to correctly identify pre-composed agents to deploy to the task or (if no relevant pre-composed agents exist) for an *agent creator* actor-agent to create a relevant agent.

**2. How to know when it is complete** — two cases:
- *Binary pass/fail*: the most unambiguous form. A test that either passes or doesn't. Use this whenever possible.
- *Stopping problem*: tasks with no natural completion state. Stopping is resolved by trade-off configurations — the task is done when acceptable trade-offs have been exhausted or unacceptable ones are about to be crossed.

**3. How to evaluate quality** — two cases:
- *Binary pass/fail tasks*: quality is expressed in efficiency terms — faster, cheaper, more compact.
- *Stopping problem tasks*: quality is partly expressed in the trade-off configuration itself and partly in any additional rubric the human specifies. Quality and completion are entangled.

These three parameters reflect well-established best practices in organisational management for defining work clearly. Bounded rationality (Simon, 1947) means humans systematically under-specify goals because full specification requires cognitive effort; surfacing these three parameters during task creation externalises that effort.

### Rubric specification spectrum

How the human specifies evaluation quality:

1. **Explicit rubric** — provided in full in the task
2. **Named rubric** — identified by name; *evaluator* actor-agent retrieves or infers it
3. **Domain standard** — field or context specified; *evaluator* actor-agent interprets what that implies
4. **Natural language** — plain text description; *evaluator* actor-agent maps to closest matching approach
5. **No specification** — rubric left entirely to the *evaluator* actor-agent, which effectively chooses arbitrarily

Point 5 is undesirable, not a failure mode in the technical sense. It represents the human not exercising the subjective judgment that is theirs to exercise. This is an instance of **control by omission**: a valid expression of human choice, but one that Agency's designers consider undesirable because it surrenders meaningmaking without intending to.

> **[Extension of current theoretical grounding]**: The current theoretical grounding identifies Goodhart's Law (Goodhart, 1975), Campbell's Law (Campbell, 1979), and Kerr's (1975) "on the folly of rewarding A, while hoping for B" as the primary evaluation failure mode — that agents optimise for the measure rather than the underlying goal. This spec identifies a prior and distinct failure mode: not specifying any rubric at all. Goodhart's Law applies once a measure exists; control by omission applies when no measure has been specified. An under-specified evaluator does not optimise for the wrong measure; it makes an arbitrary meaningmaking decision the human should have made themselves. Goodhart's Law and control by omission are sequential failure modes, not the same failure mode.

Any task system integrating with Agency should surface the three well-formed task criteria and the rubric specification spectrum as conventions during task creation (if task creation has been assigned to Agency as a task; see note below on the *task creation agent* agent type) or when tasks are received by Agency for assignment (see note below on the *assigner* agent type).

---

## Special-type agents

The following agent types — *assigner*, *evaluator*, *evolver*, *agent creator* — are each just agents with specific role components, desired outcomes, and trade-off configurations. None are privileged system components. All accumulate performance history, can be evolved, and are subject to the same selection pressure as any other agent. The only thing special about them is their target outcome: they act on the agency itself rather than on external tasks.

The human can configure any of them with any trade-off configuration, including ones that optimise for suboptimal things at the organisational level. Human commissioning is always the ultimate authority on the fitness function — consistent with principal-agent theory's requirement that the principal retain control over the agent's objective function (Jensen & Meckling, 1976).

---

## The assigner

The *assigner* is an agent type whose role components include: matching task descriptions to agent configurations, evaluating closeness of fit between tasks and role components, between tasks and desired outcomes, and between task requirements and trade-off configurations. It also uses historical performance data to weight matches.

**Task clarification as a role component** — when an *assigner* actor-agent receives an underspecified task, it should request clarification from the calling task system before assigning. This is a role component that can be tested empirically: run an *assigner* actor-agent with and without task clarification and measure whether downstream performance improves across assignment quality, actor-agent performance, evaluation quality, and organisational output. The design principle mirrors negotiated joining's proposition subprocess (Tan, 2015, pp. 114–115): before testing begins, both parties — the one proposing the role component and the organisation that will receive it — must develop a clear enough shared understanding of what is being proposed that a trial is worth running.

The *assigner*'s trade-off configuration governs when to ask versus when to proceed: always ask when critically underspecified, ask whenever any criterion is missing, or proceed with a low-confidence flag. Same role component, different trade-off configurations, different behaviour.

---

## The evaluator

The *evaluator* is an agent type whose role components may include: cardinal scale grading, ordinal scale grading, rubric interpretation, familiarity with domain-specific evaluation standards. Its desired outcome is the provision of a grade to an actor-agent that has completed a task.

*Evaluators* are not outside the system. Their grades are outputs, and those outputs can be evaluated — by a human reviewing them or by another *evaluator* agent with a more precisely specified rubric. *Evaluators* accumulate performance history and are subject to the same selection pressure as any other agent.

> **[Building on current theoretical grounding]**: The current theoretical grounding identifies proper scoring rules as the correct design principle for evaluator incentives: an *evaluator*'s expected reward should be maximised when it provides accurate assessments rather than strategically biased ones. An *evaluator* not subject to proper scoring rule incentives will drift toward evaluations that serve its own performance history rather than accurate assessments of actor-agent output. The evaluator's design should conform to this principle.

The human specifies what kind of evaluation they want via the task itself (see rubric specification spectrum above). Less specified rubrics leave more work to the *evaluator*'s role components and introduce more variance across runs.

---

## The evolver

The *evolver* is an agent type whose role components include operations that change primitives and their configurations. Its desired outcomes are specified changes at a particular level of the primitive hierarchy. Its trade-off configurations govern how aggressively it searches.

### Evolver role components (classes of mutation operation)

**Mutation** — modify existing primitives while preserving general structure. Several variants:
- *Wording mutation*: change the wording of a role component while preserving its general meaning, testing whether articulation precision affects performance
- *Role component substitution*: swap one role component for a similar-but-different one to test whether the conceptual difference is significant
- *Configuration mutation*: change how role components are combined without changing the components themselves

**Randomisation** — select from the existing primitive pool and recombine without regard for conventional attractor areas. Explores the existing primitive space without attractor bias.

**Bizarre ideation** — generate entirely novel primitives unconstrained by what exists in the primitive store, and introduce them to see if they work. Operates outside the existing primitive space.

These three classes map onto the variation mechanisms identified in Nelson & Winter's (1982) evolutionary theory: mutation of existing routines, recombination of existing routines, and generation of genuinely novel routines. Together they provide the variation necessary for selection pressure to operate on the primitive pool.

If role components are content-addressed (as in the current implementation), *evolver* operations can be framed as operations on hashes: generate a new hash, substitute hash A for hash B in a configuration, recombine hashes into new configurations. This makes mutation operations precise, composable, and verifiable.

Additional *evolver* role components from the existing implementation (mutation, crossover, gap-analysis, objective-tuning) are all valid and compatible with this framework.

### Evolver desired outcomes

Specified across two independent dimensions:

**Level** — which level of the primitive hierarchy is being targeted:
- Individual primitives (role components, desired outcomes, trade-off configurations)
- Configurations of primitives into roles
- Roles + trade-off configurations into agents
- Configurations of agents working together

**Amount** — how much change is being sought:
- Minimal (small perturbations, staying close to current configuration)
- Moderate (meaningful changes, exploring adjacent space)
- Maximal (large changes, wholesale replacement, or bizarre ideation)

### Evolver trade-off configurations

Standard patterns (speed vs. quality, aggressive exploration vs. conservative exploitation) are likely defaults. The human can specify any trade-off configuration, including domain-scoped configurations that constrain the search domain rather than just the search intensity.

> **[Potential downside: GEPA and exploitation drift]**: The GEPA backend in the current implementation uses iterative reflective evolution replacing single-shot LLM proposals. This is well-suited to trade-off configuration evolution when framed as hypothesis-testing. The potential downside is identified by March (1991): adaptive systems systematically drift toward exploitation of known-good configurations because exploration returns are uncertain and delayed. If GEPA is applied to objectives (what is worth pursuing) rather than trade-off configurations (how to pursue it), it may optimise away the uncertainty-tolerance that is one of Agency's founding purposes. This is also why the objective/trade-off configuration distinction matters architecturally: constraining automatic evolution to trade-off configurations and requiring human oversight for changes to objectives is the design response to this potential downside. In other words: require the human users commissioning Agency to choose what to apply GEPA to (objectives, tradeoff configurations, or other parameter), but provide a default selection which is either objectives (favouring exploit) or tradeoff configurations (favouring explore).

---

## The agent creator

The *agent creator* is an agent type distinct from the *assigner* and the *evolver*. Where the *assigner* operates on existing inventory and the *evolver* modifies existing inventory, the *agent creator* expands the primitive store by searching outside the agency for new role components, desired outcomes, and trade-off configurations.

Its role components include: searching research literature for effective role structures, identifying analogous domains, recognising structural similarities across fields. Its desired outcome is new primitives that are plausible candidates for the agency.

The human specifies the search domain via the *agent creator*'s trade-off configuration, along a proximity continuum:

1. **Unconstrained** — search wherever the *agent creator* judges relevant
2. **Adjacent** — search within domains the human specifies as similar to current work
3. **Distant** — search in domains the human specifies as far away (or that the *agent creator* judges to be far)
4. **Internal** — search existing projects the human has access to, importing known-good primitives or whole composed agents (federation)

The effectiveness of distant search depends on absorptive capacity (Cohen & Levinthal, 1990): the ability to recognise, assimilate, and apply external knowledge depends on the degree of relatedness between existing capabilities and the new knowledge. An agency with a rich and diverse primitive store will better recognise and absorb novel role components from distant domains; an agency with a thin store may fail to evaluate distant role components accurately even when an *agent creator* actor-agent finds them. Building absorptive capacity through adjacent search before attempting distant search reduces this failure mode.

Tan (2015, p. 120) documents the human analogue: the most disruptive role component contributions to organisations operating under genuine uncertainty came disproportionately from people whose prior experience was in domains distant from the organisation's existing work — people who brought capabilities the organisation would not have identified through internal search or adjacent recruitment alone. In Agency, the *agent creator* performs the analogous search at the primitive level.

The *agent creator*, *evolver*, and *assigner* form a pipeline: create new primitives → evolve and test configurations → assign to tasks.

---

## Task creation agent (phase 2/3)

Agency could include a *task creation agent*, an agent type whose role is to help any integrating task management system produce better-formed tasks — prompting humans to surface and articulate the subjective judgments embedded in a task before handing anything to an agent. This agent would function like a lightweight Boris (Tan, n.d.)[^4] for task specification. It operates upstream of the *assigner*: tasks pass through the *task creation agent* first, get improved or flagged if underspecified, then enter the queue.

Well-specified tasks improve every downstream component: assignment quality, actor-agent performance, evaluation consistency, and organisational output. The theoretical grounding is in bounded rationality (Simon, 1947): humans systematically under-specify goals because fully specifying them requires cognitive effort that we are motivated to avoid; a *task creation agent* externalises and reduces this effort at the point of task creation.

---

## Relationship to the current implementation (as of February 2026)

The current implementation introduces the following terminology changes from the original Agency specification:

| Original term | Current term | Note |
|---|---|---|
| Agency (the construct) | Identity | The current implementation's "Identity" refers to the individual composed agent, not the pool |
| Motivation | Objective | Current term — but this spec distinguishes Objective (what to pursue) from Trade-off configuration (how to pursue it); the current implementation's "Objective" maps to Trade-off configuration in this spec |
| Evaluation | Reward | Standard RL term |
| score / avg_score | value / mean_reward | RL convention |
| PerformanceRecord | RewardHistory | Descriptive |

**Key additions in the current implementation relevant to this spec:**

- **Pluggable reward sources** (`source: String`): enables heterogeneous reward provenance (LLM judgment, manual, outcome metrics, backward inference). Critical for the two-level reward signal and for distinguishing objective-achievement rewards from trade-off-adherence rewards.
- **GEPA backend**: iterative reflective evolution replacing single-shot LLM proposals. Well-suited to trade-off configuration evolution as hypothesis-testing when framed correctly; potential failure mode of optimising away uncertainty-tolerance if framed as pure optimisation (March, 1991).
- **ObjectiveTuning strategy**: evolves Objectives (in this spec: trade-off configurations). Correctly scoped to trade-off configurations; should not touch objectives (what is worth pursuing) without human oversight, as those are meaningmaking decisions (Tan, 2023, 2024a)[^1][^2].
- **Federation**: implemented. This spec treats federation as optional and access-controlled at the primitive level.

The most significant architectural gap between the current implementation and this spec: the primitive store does not yet exist as a separate construct from the composition cache. The current implementation holds pre-composed Identities. Separating the primitive store (role components, desired outcomes, trade-off configurations as independent indexed objects) from the composition cache (known-good assembled agents with performance history) is the key architectural change this spec requires.

**Summary of engagements with the current theoretical grounding:**
- *Section 2 (Holmstrom & Milgrom, 1991)*: The current theoretical grounding cites H&M to ground the bundled Role struct. This spec reads H&M as supporting separation of role components from desired outcomes and trade-off configurations — the opposite architectural conclusion.
- *Section 4 (two-level reward)*: The current theoretical grounding identifies this as a gap. This spec fills it.
- *Section 7 (March, 1991, exploration underproduction)*: The current theoretical grounding identifies this as a known structural tendency. This spec addresses it through the performance/learning mode continuum.
- *Section 11 (Goodhart/Campbell/Kerr)*: The current theoretical grounding identifies measurement corruption as the primary evaluation failure mode. This spec identifies control by omission as a prior and distinct failure mode.
- *Section 13 (proper scoring rules)*: The current theoretical grounding identifies proper scoring rules for *evaluator* design. This spec builds on that.

---

## References

Barney, J. (1991). Firm resources and sustained competitive advantage. *Journal of Management*, 17(1), 99–120.

Campbell, D. T. (1979). Assessing the impact of planned social change. *Evaluation and Program Planning*, 2(1), 67–90.

Cohen, L. E. (2012). Assembling jobs: A model of how tasks are bundled into and across jobs. *Organization Science*, 24(2), 432–454.

Cohen, W. M., & Levinthal, D. A. (1990). Absorptive capacity: A new perspective on learning and innovation. *Administrative Science Quarterly*, 35(1), 128–152.

Eisenhardt, K. M. (1989). Agency theory: An assessment and review. *Academy of Management Review*, 14(1), 57–74.

Goodhart, C. A. E. (1975). Problems of monetary management: The U.K. experience. In *Papers in Monetary Economics* (Vol. 1). Reserve Bank of Australia.

Hart, O., & Moore, J. (1988). Incomplete contracts and renegotiation. *Econometrica*, 56(4), 755–785.

Hayek, F. A. (1945). The use of knowledge in society. *American Economic Review*, 35(4), 519–530.

Holmstrom, B., & Milgrom, P. (1991). Multitask principal-agent analyses: Incentive contracts, asset ownership, and job design. *Journal of Law, Economics, and Organization*, 7, 24–52.

Jensen, M. C., & Meckling, W. H. (1976). Theory of the firm: Managerial behavior, agency costs and ownership structure. *Journal of Financial Economics*, 3(4), 305–360.

Jovanovic, B. (1979). Job matching and the theory of turnover. *Journal of Political Economy*, 87(5), 972–990.

Kerr, S. (1975). On the folly of rewarding A, while hoping for B. *Academy of Management Journal*, 18(4), 769–783.

Lippman, S. A., & Rumelt, R. P. (1982). Uncertain imitability: An analysis of interfirm differences in efficiency under competition. *Bell Journal of Economics*, 13(2), 418–438.

March, J. G. (1991). Exploration and exploitation in organizational learning. *Organization Science*, 2(1), 71–87.

Nelson, R. R., & Winter, S. G. (1982). *An Evolutionary Theory of Economic Change*. Harvard University Press.

Schmidt, F. L., & Hunter, J. E. (1998). The validity and utility of selection methods in personnel psychology: Practical and theoretical implications of 85 years of research findings. *Psychological Bulletin*, 124(2), 262–274.

Simon, H. A. (1947). *Administrative Behavior*. Macmillan.

Stewart, G. L., & Carson, K. P. (1997). Moving beyond the mechanistic model: An alternative approach to staffing for contemporary organizations. *Human Resource Management Review*, 7(2), 157–184.

Tan, V. (2015). Using negotiated joining to construct and fill open-ended roles in elite culinary groups. *Administrative Science Quarterly*, 60(1), 103–132.

Tan, V. (2023). What makes us human (for now)? vaughntan.org.[^1]

Tan, V. (2024a). AI's meaningmaking problem. *Uncertainty Mindset* (Substack).[^2]

Tan, V. (2024b). Where AI wins. *Uncertainty Mindset* (Substack).[^3]

Tan, V. (n.d.). Unpacking Boris. vaughntan.org.[^4]

---

[^1]: https://vaughntan.org/what-makes-us-human-for-now
[^2]: https://uncertaintymindset.substack.com/p/ai-meaningmaking
[^3]: https://uncertaintymindset.substack.com/p/where-ai-wins
[^4]: https://vaughntan.org/unpacking-boris
