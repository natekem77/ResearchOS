import 'package:flutter/material.dart';

import '../api/researchos_api.dart';
import '../design_system/researchos_design_system.dart';
import '../models/mobile_models.dart';
import 'experiment_detail_screen.dart';

class NewExperimentWizardScreen extends StatefulWidget {
  const NewExperimentWizardScreen({super.key, required this.api});

  final ResearchOsApi api;

  @override
  State<NewExperimentWizardScreen> createState() =>
      _NewExperimentWizardScreenState();
}

class _NewExperimentWizardScreenState extends State<NewExperimentWizardScreen> {
  static const _steps = [
    'Info',
    'Protocol',
    'Design',
    'Readouts',
    'Timeline',
    'Summary',
  ];

  final _title = TextEditingController();
  final _experimentId = TextEditingController();
  final _project = TextEditingController();
  final _workspace = TextEditingController();
  final _pi = TextEditingController();
  final _researcher = TextEditingController();
  final _date = TextEditingController(
    text: DateTime.now().toIso8601String().split('T').first,
  );
  final _notes = TextEditingController();
  final _protocolTitle = TextEditingController();
  final _protocolNotes = TextEditingController();
  final _blankBiologicalSystem = TextEditingController();
  final _blankSampleUnit = TextEditingController(text: 'sample');
  final _cellLine = TextEditingController();
  final _organoidBatch = TextEditingController();
  final _replicates = TextEditingController();
  final _otherReadouts = TextEditingController();
  final _ontologySearch = TextEditingController();
  final _milestoneLabel = TextEditingController();
  final _milestoneDetail = TextEditingController();
  final _treatmentCompound = TextEditingController();
  final _treatmentConcentration = TextEditingController();
  final _treatmentTimepoint = TextEditingController();

  int _step = 0;
  bool _createNewProtocol = false;
  bool _microscopy = true;
  bool _graphpad = true;
  bool _rnaseq = false;
  bool _flow = false;
  bool _createDraft = true;
  bool _startSession = false;
  bool _creating = false;
  String? _creationMode;
  String? _selectedProtocolId;
  String? _selectedGeneralProtocolId;
  String? _selectedGeneralProtocolVersionId;
  String? _error;
  Map<String, dynamic>? _created;
  List<Map<String, dynamic>> _protocols = const [];
  List<Map<String, dynamic>> _ontologyResults = const [];
  final List<String> _compounds = [];
  final List<String> _concentrations = [];
  final List<String> _timepoints = [];
  final List<String> _controls = [];
  final List<String> _readouts = [];
  final List<String> _markers = [];
  final List<Map<String, String>> _treatments = [];
  final List<Map<String, String>> _milestones = [
    {'label': 'Notebook', 'detail': 'Create reviewed notebook planning draft'},
    {'label': 'Media changes', 'detail': 'Record timing and media conditions'},
    {
      'label': 'Treatment',
      'detail': 'Apply treatment and document concentration'
    },
    {'label': 'Imaging', 'detail': 'Capture microscopy assets and markers'},
    {'label': 'Statistics', 'detail': 'Analyze quantitative readouts'},
  ];

  @override
  void initState() {
    super.initState();
    _loadProtocols();
  }

  @override
  void dispose() {
    for (final controller in [
      _title,
      _experimentId,
      _project,
      _workspace,
      _pi,
      _researcher,
      _date,
      _notes,
      _protocolTitle,
      _protocolNotes,
      _blankBiologicalSystem,
      _blankSampleUnit,
      _cellLine,
      _organoidBatch,
      _replicates,
      _otherReadouts,
      _ontologySearch,
      _milestoneLabel,
      _milestoneDetail,
      _treatmentCompound,
      _treatmentConcentration,
      _treatmentTimepoint,
    ]) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _loadProtocols() async {
    try {
      final protocols = await widget.api.generalProtocols();
      if (mounted) {
        setState(() {
          _protocols = protocols;
        });
      }
    } catch (_) {
      // Protocol selection is optional; the wizard can still create a plan.
    }
  }

  Future<void> _createBlankExperiment() async {
    if (_title.text.trim().isEmpty) {
      setState(() => _error = 'Experiment title is required.');
      return;
    }
    setState(() {
      _creating = true;
      _error = null;
    });
    try {
      final result = await widget.api.createGeneralExperiment({
        'title': _title.text.trim(),
        if (_experimentId.text.trim().isNotEmpty)
          'experiment_id': _experimentId.text.trim(),
        'biological_system': _blankBiologicalSystem.text.trim(),
        'sample_unit_type': _blankSampleUnit.text.trim().isEmpty
            ? 'sample'
            : _blankSampleUnit.text.trim(),
        'status': 'draft',
      });
      if (!mounted) return;
      setState(() => _created = result);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Blank experiment workspace created.')),
      );
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _creating = false);
    }
  }

  Future<void> _createFromProtocol() async {
    if (_title.text.trim().isEmpty ||
        _selectedGeneralProtocolId == null ||
        _selectedGeneralProtocolVersionId == null) {
      setState(
          () => _error = 'Enter a title and select an exact protocol version.');
      return;
    }
    setState(() {
      _creating = true;
      _error = null;
    });
    try {
      final result = await widget.api.createGeneralExperimentFromProtocol({
        'title': _title.text.trim(),
        if (_experimentId.text.trim().isNotEmpty)
          'experiment_id': _experimentId.text.trim(),
        'protocol_id': _selectedGeneralProtocolId,
        'protocol_version_id': _selectedGeneralProtocolVersionId,
      });
      if (!mounted) return;
      setState(() => _created = result);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Experiment created from protocol.')),
      );
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _creating = false);
    }
  }

  void _next() {
    final validation = _validateStep(_step);
    if (validation != null) {
      setState(() => _error = validation);
      return;
    }
    setState(() {
      _error = null;
      _step = (_step + 1).clamp(0, _steps.length - 1);
    });
  }

  void _back() {
    setState(() {
      _error = null;
      _step = (_step - 1).clamp(0, _steps.length - 1);
    });
  }

  String? _validateStep(int step) {
    if (step == 0) {
      if (_title.text.trim().isEmpty) {
        return 'Experiment title is required.';
      }
      if (_experimentId.text.trim().isEmpty) {
        return 'Experiment ID is required.';
      }
    }
    if (step == 1 && _createNewProtocol && _protocolTitle.text.trim().isEmpty) {
      return 'Enter a protocol title or switch back to existing protocols.';
    }
    if (step == 2 && _controls.isEmpty) {
      return 'Add at least one control before continuing.';
    }
    if (step == 3 &&
        _readouts.isEmpty &&
        _markers.isEmpty &&
        !_microscopy &&
        !_graphpad &&
        !_rnaseq &&
        !_flow) {
      return 'Add at least one expected readout.';
    }
    return null;
  }

  Future<void> _searchOntology() async {
    final query = _ontologySearch.text.trim();
    if (query.isEmpty) {
      return;
    }
    setState(() {
      _error = null;
    });
    try {
      final results = await widget.api.searchKnowledgeGraph(query);
      if (mounted) {
        setState(() {
          _ontologyResults = results;
          if (results.isEmpty) {
            _error =
                'No ontology matches yet. You can still add this as a new entity.';
          }
        });
      }
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString());
      }
    }
  }

  Future<void> _create() async {
    for (var index = 0; index < _steps.length - 1; index++) {
      final validation = _validateStep(index);
      if (validation != null) {
        setState(() {
          _step = index;
          _error = validation;
        });
        return;
      }
    }
    setState(() {
      _creating = true;
      _error = null;
    });
    try {
      final result = await widget.api.createExperiment(_payload());
      if (!mounted) {
        return;
      }
      setState(() {
        _created = result;
      });
      final experiment = result['experiment'];
      if (experiment is Map<String, dynamic>) {
        final card = ExperimentCard.fromJson(experiment);
        Navigator.of(context).pushReplacement(
          MaterialPageRoute(
            builder: (_) =>
                ExperimentDetailScreen(api: widget.api, experiment: card),
          ),
        );
      }
    } catch (error) {
      if (mounted) {
        setState(() => _error = error.toString());
      }
    } finally {
      if (mounted) {
        setState(() => _creating = false);
      }
    }
  }

  Map<String, dynamic> _payload() {
    return {
      'title': _title.text.trim(),
      'experiment_id': _experimentId.text.trim(),
      'project': _project.text.trim(),
      'workspace': _workspace.text.trim(),
      'principal_investigator': _pi.text.trim(),
      'researcher': _researcher.text.trim(),
      'date': _date.text.trim(),
      'notes': _notes.text.trim(),
      'protocol_mode': _createNewProtocol ? 'create_new' : 'select_existing',
      'protocol_id': _selectedProtocolId,
      'protocol_title': _protocolTitle.text.trim(),
      'protocol_notes': _protocolNotes.text.trim(),
      'cell_line': _cellLine.text.trim(),
      'organoid_batch': _organoidBatch.text.trim(),
      'treatments': _treatments,
      'compounds': _compounds,
      'concentrations': _concentrations,
      'timepoints': _timepoints,
      'replicates': _replicates.text.trim(),
      'controls': _controls,
      'readouts': _readouts,
      'markers': _markers,
      'microscopy': _microscopy,
      'graphpad': _graphpad,
      'rnaseq': _rnaseq,
      'flow_cytometry': _flow,
      'other_readouts': _otherReadouts.text.trim(),
      'milestones': _milestones,
      'create_notebook_draft': _createDraft,
      'start_session': _startSession,
    };
  }

  @override
  Widget build(BuildContext context) {
    if (_creationMode == null) {
      return _ExperimentCreationModeLanding(
        onSelected: (mode) => setState(() {
          _creationMode = mode;
          _error = null;
        }),
      );
    }
    if (_creationMode == 'blank') {
      return _BlankExperimentFlow(
        title: _title,
        experimentId: _experimentId,
        biologicalSystem: _blankBiologicalSystem,
        sampleUnit: _blankSampleUnit,
        creating: _creating,
        error: _error,
        created: _created,
        onBack: () => setState(() => _creationMode = null),
        onCreate: _createBlankExperiment,
      );
    }
    if (_creationMode == 'protocol') {
      return _StartFromProtocolFlow(
        title: _title,
        experimentId: _experimentId,
        protocols: _protocols,
        selectedVersionId: _selectedGeneralProtocolVersionId,
        creating: _creating,
        error: _error,
        created: _created,
        onBack: () => setState(() => _creationMode = null),
        onProtocolSelected: (protocolId, versionId) => setState(() {
          _selectedGeneralProtocolId = protocolId;
          _selectedGeneralProtocolVersionId = versionId;
        }),
        onCreate: _createFromProtocol,
      );
    }
    if (_creationMode == 'describe') {
      return _DescribeExperimentCopilotFlow(
        api: widget.api,
        onBack: () => setState(() => _creationMode = null),
      );
    }
    if (_creationMode == 'import') {
      return _FutureCreationMode(
        mode: _creationMode!,
        onBack: () => setState(() => _creationMode = null),
      );
    }
    final isSummary = _step == _steps.length - 1;
    return Scaffold(
      appBar: AppBar(
        title: const Text('New Experiment'),
      ),
      body: SafeArea(
        child: ListView(
          padding: ResearchOsSpacing.screen,
          children: [
            ResearchOsCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('New Experiment Wizard',
                      style: Theme.of(context).textTheme.headlineSmall),
                  const SizedBox(height: ResearchOsSpacing.sm),
                  const Text(
                    'Plan the experiment, prepare a notebook draft, initialize workflow state, and keep OneNote write-back disabled until approved.',
                  ),
                  const SizedBox(height: ResearchOsSpacing.lg),
                  _ProgressIndicator(step: _step, steps: _steps),
                ],
              ),
            ),
            if (_error != null) ...[
              const SizedBox(height: ResearchOsSpacing.md),
              ResearchOsCopilotCard(
                title: 'Check this step',
                message: _error!,
                level: CopilotCardLevel.warning,
              ),
            ],
            const SizedBox(height: ResearchOsSpacing.md),
            AnimatedSwitcher(
              duration: ResearchOsAnimation.normal,
              child: KeyedSubtree(
                key: ValueKey(_step),
                child: _stepContent(),
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.lg),
            Row(
              children: [
                if (_step > 0)
                  Expanded(
                    child: OutlinedButton.icon(
                      onPressed: _creating ? null : _back,
                      icon: const Icon(Icons.arrow_back),
                      label: const Text('Back'),
                    ),
                  ),
                if (_step > 0) const SizedBox(width: ResearchOsSpacing.md),
                Expanded(
                  child: FilledButton.icon(
                    onPressed: _creating ? null : (isSummary ? _create : _next),
                    icon: Icon(isSummary
                        ? Icons.check_circle_outline
                        : Icons.arrow_forward),
                    label: Text(_creating
                        ? 'Creating...'
                        : isSummary
                            ? 'Create experiment'
                            : 'Continue'),
                  ),
                ),
              ],
            ),
            if (_created != null) ...[
              const SizedBox(height: ResearchOsSpacing.md),
              ResearchOsCopilotCard(
                title: 'Experiment created',
                message: _created!['message']?.toString() ??
                    'Mundi created the planned experiment.',
                level: CopilotCardLevel.success,
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _stepContent() {
    return switch (_step) {
      0 => _ExperimentInfoStep(
          title: _title,
          experimentId: _experimentId,
          project: _project,
          workspace: _workspace,
          pi: _pi,
          researcher: _researcher,
          date: _date,
          notes: _notes,
        ),
      1 => _ProtocolStep(
          protocols: _protocols,
          createNew: _createNewProtocol,
          selectedProtocolId: _selectedProtocolId,
          protocolTitle: _protocolTitle,
          protocolNotes: _protocolNotes,
          onCreateModeChanged: (value) {
            setState(() => _createNewProtocol = value);
          },
          onProtocolSelected: (protocol) {
            setState(() {
              _selectedProtocolId = protocol['protocol_id']?.toString() ??
                  protocol['id']?.toString();
              _protocolTitle.text = protocol['title']?.toString() ??
                  protocol['name']?.toString() ??
                  '';
            });
          },
        ),
      2 => _DesignStep(
          cellLine: _cellLine,
          organoidBatch: _organoidBatch,
          replicates: _replicates,
          compounds: _compounds,
          concentrations: _concentrations,
          timepoints: _timepoints,
          controls: _controls,
          treatments: _treatments,
          treatmentCompound: _treatmentCompound,
          treatmentConcentration: _treatmentConcentration,
          treatmentTimepoint: _treatmentTimepoint,
          onChanged: () => setState(() {}),
        ),
      3 => _ReadoutsStep(
          readouts: _readouts,
          markers: _markers,
          otherReadouts: _otherReadouts,
          ontologySearch: _ontologySearch,
          ontologyResults: _ontologyResults,
          microscopy: _microscopy,
          graphpad: _graphpad,
          rnaseq: _rnaseq,
          flow: _flow,
          onSearch: _searchOntology,
          onChanged: () => setState(() {}),
          onMicroscopy: (value) => setState(() => _microscopy = value),
          onGraphPad: (value) => setState(() => _graphpad = value),
          onRnaseq: (value) => setState(() => _rnaseq = value),
          onFlow: (value) => setState(() => _flow = value),
        ),
      4 => _TimelineStep(
          milestones: _milestones,
          label: _milestoneLabel,
          detail: _milestoneDetail,
          onChanged: () => setState(() {}),
        ),
      _ => _SummaryStep(
          payload: _payload(),
          createDraft: _createDraft,
          startSession: _startSession,
          onCreateDraft: (value) => setState(() => _createDraft = value),
          onStartSession: (value) => setState(() => _startSession = value),
          onEditStep: (step) => setState(() => _step = step),
        ),
    };
  }
}

class _ProgressIndicator extends StatelessWidget {
  const _ProgressIndicator({required this.step, required this.steps});

  final int step;
  final List<String> steps;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Row(
          children: [
            for (var index = 0; index < steps.length; index++) ...[
              Expanded(
                child: AnimatedContainer(
                  duration: ResearchOsAnimation.normal,
                  height: index == step ? 10 : 6,
                  decoration: BoxDecoration(
                    color: index <= step
                        ? Theme.of(context).colorScheme.primary
                        : Theme.of(context).colorScheme.outlineVariant,
                    borderRadius: ResearchOsSpacing.compactRadius,
                  ),
                ),
              ),
              if (index != steps.length - 1)
                const SizedBox(width: ResearchOsSpacing.xs),
            ],
          ],
        ),
        const SizedBox(height: ResearchOsSpacing.sm),
        Row(
          children: [
            Text('Step ${step + 1} of ${steps.length}',
                style: Theme.of(context).textTheme.labelLarge),
            const SizedBox(width: ResearchOsSpacing.sm),
            Expanded(
              child: Text(
                steps[step],
                textAlign: TextAlign.end,
                style: Theme.of(context).textTheme.labelLarge,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _ExperimentInfoStep extends StatelessWidget {
  const _ExperimentInfoStep({
    required this.title,
    required this.experimentId,
    required this.project,
    required this.workspace,
    required this.pi,
    required this.researcher,
    required this.date,
    required this.notes,
  });

  final TextEditingController title;
  final TextEditingController experimentId;
  final TextEditingController project;
  final TextEditingController workspace;
  final TextEditingController pi;
  final TextEditingController researcher;
  final TextEditingController date;
  final TextEditingController notes;

  @override
  Widget build(BuildContext context) {
    return _StepCard(
      title: 'Experiment Information',
      icon: Icons.assignment_outlined,
      children: [
        _WizardField(
            controller: title, label: 'Experiment title', required: true),
        _WizardField(
            controller: experimentId, label: 'Experiment ID', required: true),
        _WizardField(controller: project, label: 'Project'),
        _WizardField(controller: workspace, label: 'Workspace'),
        _WizardField(controller: pi, label: 'Principal investigator'),
        _WizardField(controller: researcher, label: 'Researcher'),
        _WizardField(controller: date, label: 'Date'),
        _WizardField(controller: notes, label: 'Notes', maxLines: 4),
      ],
    );
  }
}

class _ProtocolStep extends StatelessWidget {
  const _ProtocolStep({
    required this.protocols,
    required this.createNew,
    required this.selectedProtocolId,
    required this.protocolTitle,
    required this.protocolNotes,
    required this.onCreateModeChanged,
    required this.onProtocolSelected,
  });

  final List<Map<String, dynamic>> protocols;
  final bool createNew;
  final String? selectedProtocolId;
  final TextEditingController protocolTitle;
  final TextEditingController protocolNotes;
  final ValueChanged<bool> onCreateModeChanged;
  final ValueChanged<Map<String, dynamic>> onProtocolSelected;

  @override
  Widget build(BuildContext context) {
    return _StepCard(
      title: 'Protocol',
      icon: Icons.fact_check_outlined,
      children: [
        SwitchListTile(
          value: createNew,
          onChanged: onCreateModeChanged,
          title: const Text('Create new protocol'),
          subtitle:
              const Text('Otherwise select an existing protocol if available.'),
        ),
        if (!createNew) ...[
          if (protocols.isEmpty)
            const ResearchOsEmptyState(
              title: 'No protocols yet',
              message:
                  'Create a protocol title below or continue with a planning note.',
              icon: Icons.description_outlined,
            )
          else
            Wrap(
              spacing: ResearchOsSpacing.sm,
              runSpacing: ResearchOsSpacing.sm,
              children: [
                for (final protocol in protocols.take(8))
                  ChoiceChip(
                    label: Text(protocol['title']?.toString() ??
                        protocol['name']?.toString() ??
                        'Protocol'),
                    selected: selectedProtocolId ==
                        (protocol['protocol_id']?.toString() ??
                            protocol['id']?.toString()),
                    onSelected: (_) => onProtocolSelected(protocol),
                  ),
              ],
            ),
          const SizedBox(height: ResearchOsSpacing.md),
        ],
        _WizardField(controller: protocolTitle, label: 'Protocol title'),
        _WizardField(
            controller: protocolNotes, label: 'Protocol notes', maxLines: 4),
      ],
    );
  }
}

class _DesignStep extends StatelessWidget {
  const _DesignStep({
    required this.cellLine,
    required this.organoidBatch,
    required this.replicates,
    required this.compounds,
    required this.concentrations,
    required this.timepoints,
    required this.controls,
    required this.treatments,
    required this.treatmentCompound,
    required this.treatmentConcentration,
    required this.treatmentTimepoint,
    required this.onChanged,
  });

  final TextEditingController cellLine;
  final TextEditingController organoidBatch;
  final TextEditingController replicates;
  final List<String> compounds;
  final List<String> concentrations;
  final List<String> timepoints;
  final List<String> controls;
  final List<Map<String, String>> treatments;
  final TextEditingController treatmentCompound;
  final TextEditingController treatmentConcentration;
  final TextEditingController treatmentTimepoint;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    return _StepCard(
      title: 'Experimental Design',
      icon: Icons.schema_outlined,
      children: [
        _WizardField(controller: cellLine, label: 'Cell line'),
        _WizardField(controller: organoidBatch, label: 'Organoid batch'),
        _WizardField(controller: replicates, label: 'Replicates'),
        _ChipInput(label: 'Compounds', values: compounds, onChanged: onChanged),
        _ChipInput(
            label: 'Concentrations',
            values: concentrations,
            onChanged: onChanged),
        _ChipInput(
            label: 'Timepoints', values: timepoints, onChanged: onChanged),
        _ChipInput(label: 'Controls', values: controls, onChanged: onChanged),
        const ResearchOsSectionHeader(title: 'Treatments'),
        Row(
          children: [
            Expanded(
                child: _WizardField(
                    controller: treatmentCompound, label: 'Compound')),
            const SizedBox(width: ResearchOsSpacing.sm),
            Expanded(
                child: _WizardField(
                    controller: treatmentConcentration, label: 'Dose')),
          ],
        ),
        _WizardField(controller: treatmentTimepoint, label: 'Timepoint'),
        FilledButton.icon(
          onPressed: () {
            final treatment = {
              'compound': treatmentCompound.text.trim(),
              'concentration': treatmentConcentration.text.trim(),
              'timepoint': treatmentTimepoint.text.trim(),
            };
            if (treatment.values.any((value) => value.isNotEmpty)) {
              treatments.add(treatment);
              treatmentCompound.clear();
              treatmentConcentration.clear();
              treatmentTimepoint.clear();
              onChanged();
            }
          },
          icon: const Icon(Icons.add),
          label: const Text('Add treatment'),
        ),
        Wrap(
          spacing: ResearchOsSpacing.sm,
          children: [
            for (final treatment in treatments)
              InputChip(
                label: Text([
                  treatment['compound'],
                  treatment['concentration'],
                  treatment['timepoint'],
                ].where((item) => item != null && item.isNotEmpty).join(' / ')),
                onDeleted: () {
                  treatments.remove(treatment);
                  onChanged();
                },
              ),
          ],
        ),
      ],
    );
  }
}

class _ReadoutsStep extends StatelessWidget {
  const _ReadoutsStep({
    required this.readouts,
    required this.markers,
    required this.otherReadouts,
    required this.ontologySearch,
    required this.ontologyResults,
    required this.microscopy,
    required this.graphpad,
    required this.rnaseq,
    required this.flow,
    required this.onSearch,
    required this.onChanged,
    required this.onMicroscopy,
    required this.onGraphPad,
    required this.onRnaseq,
    required this.onFlow,
  });

  final List<String> readouts;
  final List<String> markers;
  final TextEditingController otherReadouts;
  final TextEditingController ontologySearch;
  final List<Map<String, dynamic>> ontologyResults;
  final bool microscopy;
  final bool graphpad;
  final bool rnaseq;
  final bool flow;
  final Future<void> Function() onSearch;
  final VoidCallback onChanged;
  final ValueChanged<bool> onMicroscopy;
  final ValueChanged<bool> onGraphPad;
  final ValueChanged<bool> onRnaseq;
  final ValueChanged<bool> onFlow;

  @override
  Widget build(BuildContext context) {
    return _StepCard(
      title: 'Expected Readouts',
      icon: Icons.query_stats_outlined,
      children: [
        _ChipInput(label: 'Readouts', values: readouts, onChanged: onChanged),
        _ChipInput(
          label: 'Markers / entities',
          values: markers,
          onChanged: onChanged,
        ),
        const SizedBox(height: ResearchOsSpacing.sm),
        Row(
          children: [
            Expanded(
              child: _WizardField(
                controller: ontologySearch,
                label: 'Search ontology',
              ),
            ),
            const SizedBox(width: ResearchOsSpacing.sm),
            IconButton.filled(
              tooltip: 'Search ontology',
              onPressed: onSearch,
              icon: const Icon(Icons.search),
            ),
          ],
        ),
        Wrap(
          spacing: ResearchOsSpacing.sm,
          runSpacing: ResearchOsSpacing.sm,
          children: [
            for (final result in ontologyResults.take(12))
              ActionChip(
                label: Text(result['entity']?.toString() ??
                    result['name']?.toString() ??
                    result['title']?.toString() ??
                    'Entity'),
                avatar: const Icon(Icons.hub_outlined, size: 16),
                onPressed: () {
                  final label = result['entity']?.toString() ??
                      result['name']?.toString() ??
                      result['title']?.toString();
                  if (label != null &&
                      label.isNotEmpty &&
                      !markers.contains(label)) {
                    markers.add(label);
                    onChanged();
                  }
                },
              ),
          ],
        ),
        const ResearchOsSectionHeader(title: 'Readout types'),
        SwitchListTile(
            value: microscopy,
            onChanged: onMicroscopy,
            title: const Text('Microscopy')),
        SwitchListTile(
            value: graphpad,
            onChanged: onGraphPad,
            title: const Text('GraphPad')),
        SwitchListTile(
            value: rnaseq, onChanged: onRnaseq, title: const Text('RNA-seq')),
        SwitchListTile(
            value: flow,
            onChanged: onFlow,
            title: const Text('Flow cytometry')),
        _WizardField(
            controller: otherReadouts, label: 'Other readouts', maxLines: 3),
      ],
    );
  }
}

class _TimelineStep extends StatelessWidget {
  const _TimelineStep({
    required this.milestones,
    required this.label,
    required this.detail,
    required this.onChanged,
  });

  final List<Map<String, String>> milestones;
  final TextEditingController label;
  final TextEditingController detail;
  final VoidCallback onChanged;

  @override
  Widget build(BuildContext context) {
    return _StepCard(
      title: 'Timeline',
      icon: Icons.timeline_outlined,
      children: [
        _WizardField(controller: label, label: 'Milestone'),
        _WizardField(controller: detail, label: 'Details'),
        FilledButton.icon(
          onPressed: () {
            if (label.text.trim().isNotEmpty) {
              milestones.add({
                'label': label.text.trim(),
                'detail': detail.text.trim(),
              });
              label.clear();
              detail.clear();
              onChanged();
            }
          },
          icon: const Icon(Icons.add),
          label: const Text('Add milestone'),
        ),
        const SizedBox(height: ResearchOsSpacing.md),
        for (final item in milestones)
          ResearchOsTimelineCard(
            title: item['label'] ?? 'Milestone',
            timestamp: item['date'] ?? 'Planned',
            eventType: 'planned',
            description: item['detail'],
            onTap: () {
              milestones.remove(item);
              onChanged();
            },
          ),
      ],
    );
  }
}

class _SummaryStep extends StatelessWidget {
  const _SummaryStep({
    required this.payload,
    required this.createDraft,
    required this.startSession,
    required this.onCreateDraft,
    required this.onStartSession,
    required this.onEditStep,
  });

  final Map<String, dynamic> payload;
  final bool createDraft;
  final bool startSession;
  final ValueChanged<bool> onCreateDraft;
  final ValueChanged<bool> onStartSession;
  final ValueChanged<int> onEditStep;

  @override
  Widget build(BuildContext context) {
    return _StepCard(
      title: 'Summary',
      icon: Icons.preview_outlined,
      children: [
        _SummaryRow('Experiment', payload['title']?.toString() ?? '',
            () => onEditStep(0)),
        _SummaryRow('ID', payload['experiment_id']?.toString() ?? '',
            () => onEditStep(0)),
        _SummaryRow('Protocol', payload['protocol_title']?.toString() ?? 'TBD',
            () => onEditStep(1)),
        _SummaryRow(
            'Design', _summaryList(payload['compounds']), () => onEditStep(2)),
        _SummaryRow(
            'Controls', _summaryList(payload['controls']), () => onEditStep(2)),
        _SummaryRow(
            'Readouts', _summaryList(payload['readouts']), () => onEditStep(3)),
        _SummaryRow(
            'Entities', _summaryList(payload['markers']), () => onEditStep(3)),
        _SummaryRow('Milestones', '${(payload['milestones'] as List).length}',
            () => onEditStep(4)),
        const SizedBox(height: ResearchOsSpacing.md),
        SwitchListTile(
          value: createDraft,
          onChanged: onCreateDraft,
          title: const Text('Create notebook draft'),
          subtitle:
              const Text('Saves a Mundi draft that can be copied or exported.'),
        ),
        SwitchListTile(
          value: startSession,
          onChanged: onStartSession,
          title: const Text('Start Bench Mode session'),
          subtitle: const Text('Optional. Start only if work begins now.'),
        ),
        const ResearchOsCopilotCard(
          title: 'OneNote write-back',
          message:
              'Save to OneNote remains disabled until UCSD IT approves OneNote create/write permissions.',
          level: CopilotCardLevel.warning,
        ),
      ],
    );
  }
}

class _SummaryRow extends StatelessWidget {
  const _SummaryRow(this.label, this.value, this.onEdit);

  final String label;
  final String value;
  final VoidCallback onEdit;

  @override
  Widget build(BuildContext context) {
    return ListTile(
      contentPadding: EdgeInsets.zero,
      title: Text(label),
      subtitle: Text(value.isEmpty ? 'TBD' : value),
      trailing: IconButton(
        tooltip: 'Edit $label',
        onPressed: onEdit,
        icon: const Icon(Icons.edit_outlined),
      ),
    );
  }
}

class _StepCard extends StatelessWidget {
  const _StepCard({
    required this.title,
    required this.icon,
    required this.children,
  });

  final String title;
  final IconData icon;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return ResearchOsCard(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(
            children: [
              Icon(icon, color: Theme.of(context).colorScheme.primary),
              const SizedBox(width: ResearchOsSpacing.sm),
              Expanded(
                  child: Text(title,
                      style: Theme.of(context).textTheme.titleLarge)),
            ],
          ),
          const SizedBox(height: ResearchOsSpacing.lg),
          ...children,
        ],
      ),
    );
  }
}

class _WizardField extends StatelessWidget {
  const _WizardField({
    required this.controller,
    required this.label,
    this.required = false,
    this.maxLines = 1,
  });

  final TextEditingController controller;
  final String label;
  final bool required;
  final int maxLines;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: ResearchOsSpacing.md),
      child: TextField(
        controller: controller,
        maxLines: maxLines,
        decoration: InputDecoration(
          labelText: required ? '$label *' : label,
          border: const OutlineInputBorder(),
        ),
      ),
    );
  }
}

class _ExperimentCreationModeLanding extends StatelessWidget {
  const _ExperimentCreationModeLanding({required this.onSelected});

  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    final modes = [
      (
        'blank',
        'Blank Experiment',
        'Start with a narrative notebook and optional structured plan.',
        Icons.note_add_outlined
      ),
      (
        'protocol',
        'Start from Protocol',
        'Select an exact protocol version and inherit linked events.',
        Icons.article_outlined
      ),
      (
        'guided',
        'Guided Builder',
        'Walk through basics, design, readouts, timeline, and review.',
        Icons.route_outlined
      ),
      (
        'describe',
        'Describe Experiment',
        'Turn typed or spoken scientific narrative into a reviewed draft.',
        Icons.auto_awesome_outlined
      ),
      (
        'import',
        'Import Spreadsheet',
        'Future mapped spreadsheet import into the generalized schema.',
        Icons.table_chart_outlined
      ),
    ];
    return Scaffold(
      appBar: AppBar(title: const Text('Create Experiment')),
      body: SafeArea(
        child: ListView(
          padding: ResearchOsSpacing.screen,
          children: [
            ResearchOsCard(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text('Choose how to begin',
                      style: Theme.of(context).textTheme.headlineSmall),
                  const SizedBox(height: ResearchOsSpacing.sm),
                  const Text(
                    'Mundi keeps free-form scientific notes and structured design data synchronized, without overwriting narrative notes.',
                  ),
                ],
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.lg),
            for (final mode in modes) ...[
              ResearchOsInfoCard(
                title: mode.$2,
                subtitle: mode.$3,
                icon: mode.$4,
                onTap: () => onSelected(mode.$1),
              ),
              const SizedBox(height: ResearchOsSpacing.sm),
            ],
          ],
        ),
      ),
    );
  }
}

class _BlankExperimentFlow extends StatelessWidget {
  const _BlankExperimentFlow({
    required this.title,
    required this.experimentId,
    required this.biologicalSystem,
    required this.sampleUnit,
    required this.creating,
    required this.error,
    required this.created,
    required this.onBack,
    required this.onCreate,
  });

  final TextEditingController title;
  final TextEditingController experimentId;
  final TextEditingController biologicalSystem;
  final TextEditingController sampleUnit;
  final bool creating;
  final String? error;
  final Map<String, dynamic>? created;
  final VoidCallback onBack;
  final VoidCallback onCreate;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Blank Experiment'),
        leading: BackButton(onPressed: onBack),
      ),
      body: SafeArea(
        child: ListView(
          padding: ResearchOsSpacing.screen,
          children: [
            const ResearchOsCopilotCard(
              title: 'General-purpose workspace',
              message:
                  'Use any biological system and sample unit. Structured data can be added later and will not overwrite notebook notes.',
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            _WizardField(
                controller: title, label: 'Experiment title', required: true),
            _WizardField(controller: experimentId, label: 'Experiment ID'),
            _WizardField(
                controller: biologicalSystem, label: 'Biological system'),
            _WizardField(controller: sampleUnit, label: 'Sample unit'),
            if (error != null) ...[
              ResearchOsCopilotCard(
                title: 'Check this experiment',
                message: error!,
                level: CopilotCardLevel.warning,
              ),
              const SizedBox(height: ResearchOsSpacing.md),
            ],
            FilledButton.icon(
              onPressed: creating ? null : onCreate,
              icon: const Icon(Icons.add_circle_outline),
              label: Text(creating ? 'Creating...' : 'Create Blank Experiment'),
            ),
            if (created != null) ...[
              const SizedBox(height: ResearchOsSpacing.md),
              const ResearchOsCopilotCard(
                title: 'Workspace created',
                message:
                    'Open the experiment from the Experiments list to edit the notebook and structured plan.',
                level: CopilotCardLevel.success,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _StartFromProtocolFlow extends StatelessWidget {
  const _StartFromProtocolFlow({
    required this.title,
    required this.experimentId,
    required this.protocols,
    required this.selectedVersionId,
    required this.creating,
    required this.error,
    required this.created,
    required this.onBack,
    required this.onProtocolSelected,
    required this.onCreate,
  });

  final TextEditingController title;
  final TextEditingController experimentId;
  final List<Map<String, dynamic>> protocols;
  final String? selectedVersionId;
  final bool creating;
  final String? error;
  final Map<String, dynamic>? created;
  final VoidCallback onBack;
  final void Function(String protocolId, String versionId) onProtocolSelected;
  final VoidCallback onCreate;

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Start from Protocol'),
        leading: BackButton(onPressed: onBack),
      ),
      body: SafeArea(
        child: ListView(
          padding: ResearchOsSpacing.screen,
          children: [
            const ResearchOsCopilotCard(
              title: 'Protocol version lock',
              message:
                  'The new experiment links to the exact protocol version selected here. Later protocol edits will not silently alter this experiment.',
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            _WizardField(
                controller: title, label: 'Experiment title', required: true),
            _WizardField(controller: experimentId, label: 'Experiment ID'),
            const ResearchOsSectionHeader(title: 'Protocol versions'),
            if (protocols.isEmpty)
              const ResearchOsEmptyState(
                title: 'No protocols available',
                message:
                    'Demo protocol data will appear after the backend initializes.',
                icon: Icons.article_outlined,
              )
            else
              for (final protocol in protocols)
                for (final version
                    in (protocol['versions'] as List? ?? const []))
                  if (version is Map<String, dynamic>)
                    RadioListTile<String>(
                      value: version['protocol_version_id'].toString(),
                      // ignore: deprecated_member_use
                      groupValue: selectedVersionId,
                      // ignore: deprecated_member_use
                      onChanged: (_) => onProtocolSelected(
                        protocol['protocol_id'].toString(),
                        version['protocol_version_id'].toString(),
                      ),
                      title: Text(protocol['title']?.toString() ?? 'Protocol'),
                      subtitle: Text(
                        'Version ${version['version_label'] ?? version['protocol_version_id']}',
                      ),
                    ),
            if (error != null) ...[
              ResearchOsCopilotCard(
                title: 'Check this protocol setup',
                message: error!,
                level: CopilotCardLevel.warning,
              ),
              const SizedBox(height: ResearchOsSpacing.md),
            ],
            FilledButton.icon(
              onPressed: creating ? null : onCreate,
              icon: const Icon(Icons.account_tree_outlined),
              label: Text(creating ? 'Creating...' : 'Create from Protocol'),
            ),
            if (created != null) ...[
              const SizedBox(height: ResearchOsSpacing.md),
              const ResearchOsCopilotCard(
                title: 'Protocol-derived experiment created',
                message:
                    'Inherited protocol events are labeled and remain linked to the original protocol version.',
                level: CopilotCardLevel.success,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _DescribeExperimentCopilotFlow extends StatefulWidget {
  const _DescribeExperimentCopilotFlow({
    required this.api,
    required this.onBack,
  });

  final ResearchOsApi api;
  final VoidCallback onBack;

  @override
  State<_DescribeExperimentCopilotFlow> createState() =>
      _DescribeExperimentCopilotFlowState();
}

class _DescribeExperimentCopilotFlowState
    extends State<_DescribeExperimentCopilotFlow> {
  final _narrative = TextEditingController();
  final _title = TextEditingController();
  final _experimentId = TextEditingController();
  final Map<String, TextEditingController> _answers = {};
  Map<String, dynamic>? _draft;
  bool _loading = false;
  bool _approving = false;
  String? _error;

  @override
  void dispose() {
    _narrative.dispose();
    _title.dispose();
    _experimentId.dispose();
    for (final controller in _answers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  Future<void> _loadDemoNarrative() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final demo = await widget.api.experimentCopilotDemoNarrative();
      _narrative.text = demo['narrative']?.toString() ?? '';
      _title.text = demo['title']?.toString() ?? '';
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _generateDraft() async {
    if (_narrative.text.trim().isEmpty) {
      setState(() => _error = 'Describe the planned experiment first.');
      return;
    }
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final draft = await widget.api.createExperimentCopilotDraft(
        narrative: _narrative.text.trim(),
      );
      if (!mounted) return;
      setState(() {
        _draft = draft;
        final inferredTitle = _draftMap['title']?.toString();
        if (_title.text.trim().isEmpty && inferredTitle != null) {
          _title.text = inferredTitle;
        }
        _ensureAnswerControllers();
      });
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _submitClarifications() async {
    final sessionId = _draft?['session_id']?.toString();
    if (sessionId == null) return;
    final answers = {
      for (final entry in _answers.entries)
        if (entry.value.text.trim().isNotEmpty)
          entry.key: entry.value.text.trim(),
    };
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final updated = await widget.api.clarifyExperimentCopilotDraft(
        sessionId: sessionId,
        answers: answers,
      );
      if (mounted) {
        setState(() {
          _draft = updated;
          _ensureAnswerControllers();
        });
      }
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _loading = false);
    }
  }

  Future<void> _approveDraft() async {
    final sessionId = _draft?['session_id']?.toString();
    if (sessionId == null) return;
    setState(() {
      _approving = true;
      _error = null;
    });
    try {
      final approved = await widget.api.approveExperimentCopilotDraft(
        sessionId: sessionId,
        title: _title.text,
        experimentId: _experimentId.text,
      );
      if (!mounted) return;
      setState(() => _draft = approved);
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Draft experiment created.')),
      );
    } catch (error) {
      if (mounted) setState(() => _error = error.toString());
    } finally {
      if (mounted) setState(() => _approving = false);
    }
  }

  Map<String, dynamic> get _draftMap =>
      (_draft?['draft'] as Map?)?.cast<String, dynamic>() ??
      const <String, dynamic>{};

  void _ensureAnswerControllers() {
    final questions =
        (_draftMap['clarification_questions'] as List? ?? const [])
            .whereType<Map>()
            .map((item) => item.cast<String, dynamic>());
    for (final question in questions) {
      final id = question['question_id']?.toString();
      if (id != null && !_answers.containsKey(id)) {
        _answers[id] =
            TextEditingController(text: question['answer']?.toString() ?? '');
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final draft = _draftMap;
    final status = _draft?['status']?.toString() ?? 'not_started';
    final createdExperiment =
        (_draft?['experiment'] as Map?)?.cast<String, dynamic>();
    return Scaffold(
      appBar: AppBar(
        title: const Text('Describe Experiment'),
        leading: BackButton(onPressed: widget.onBack),
      ),
      body: SafeArea(
        child: ListView(
          padding: ResearchOsSpacing.screen,
          children: [
            const ResearchOsCopilotCard(
              title: 'Experiment Design Copilot',
              message:
                  'Describe the experiment in plain scientific language. Mundi drafts structure, asks clarifying questions, and waits for approval before creating anything.',
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            Row(
              children: [
                Expanded(
                  child: OutlinedButton.icon(
                    onPressed: _loading ? null : _loadDemoNarrative,
                    icon: const Icon(Icons.science_outlined),
                    label: const Text('Load SAG demo'),
                  ),
                ),
                const SizedBox(width: ResearchOsSpacing.sm),
                Expanded(
                  child: FilledButton.icon(
                    onPressed: _loading ? null : _generateDraft,
                    icon: const Icon(Icons.auto_awesome_outlined),
                    label: Text(_loading ? 'Working...' : 'Generate draft'),
                  ),
                ),
              ],
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            TextField(
              controller: _narrative,
              minLines: 10,
              maxLines: 18,
              decoration: const InputDecoration(
                labelText: 'Scientific narrative / voice transcript',
                alignLabelWithHint: true,
                border: OutlineInputBorder(),
              ),
            ),
            const SizedBox(height: ResearchOsSpacing.md),
            _WizardField(controller: _title, label: 'Draft title'),
            _WizardField(controller: _experimentId, label: 'Experiment ID'),
            if (_error != null) ...[
              ResearchOsCopilotCard(
                title: 'Copilot needs attention',
                message: _error!,
                level: CopilotCardLevel.warning,
              ),
              const SizedBox(height: ResearchOsSpacing.md),
            ],
            if (draft.isNotEmpty) ...[
              _CopilotDraftStatus(status: status),
              _CopilotSection(
                title: 'Extracted Structure',
                children: [
                  _FactRow('Biological system', draft['biological_system']),
                  _FactRow('Sample unit', draft['sample_unit']),
                  _FactRow('Protocol',
                      (draft['protocol'] as Map?)?['title'] ?? 'Unknown'),
                  _FactRow(
                      'Expected duration',
                      draft['expected_duration'] == null
                          ? null
                          : 'D${draft['expected_duration']}'),
                ],
              ),
              _CopilotListSection(
                  title: 'Cohorts',
                  items: _maps(draft['cohorts']),
                  label: 'name'),
              _CopilotListSection(
                  title: 'Conditions',
                  items: _maps(draft['conditions']),
                  label: 'name'),
              _CopilotListSection(
                  title: 'Treatments',
                  items: _maps(draft['interventions']),
                  label: 'name'),
              _CopilotTimeline(events: _maps(draft['timeline_preview'])),
              _ClarificationCards(
                questions: _maps(draft['clarification_questions']),
                controllers: _answers,
                onSubmit: _submitClarifications,
                loading: _loading,
              ),
              _EvidenceCards(evidence: _maps(draft['evidence'])),
              _CopilotSection(
                title: 'Sample Planning',
                children: [
                  Text((draft['sample_planning'] as Map?)?['message']
                          ?.toString() ??
                      'No sample planning preview available.'),
                ],
              ),
              const SizedBox(height: ResearchOsSpacing.md),
              FilledButton.icon(
                onPressed: status == 'awaiting_approval' && !_approving
                    ? _approveDraft
                    : null,
                icon: _approving
                    ? const SizedBox.square(
                        dimension: 18,
                        child: CircularProgressIndicator(strokeWidth: 2),
                      )
                    : const Icon(Icons.verified_outlined),
                label: Text(_approving
                    ? 'Creating draft...'
                    : 'Approve Draft and Create Experiment'),
              ),
            ],
            if (createdExperiment != null) ...[
              const SizedBox(height: ResearchOsSpacing.md),
              ResearchOsCopilotCard(
                title: 'Draft experiment created',
                message:
                    '${createdExperiment['title'] ?? 'Experiment'} is now available as a draft workspace.',
                level: CopilotCardLevel.success,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _CopilotDraftStatus extends StatelessWidget {
  const _CopilotDraftStatus({required this.status});

  final String status;

  @override
  Widget build(BuildContext context) {
    return ResearchOsInfoCard(
      title: status == 'awaiting_approval'
          ? 'Ready for researcher approval'
          : 'Clarification required',
      subtitle:
          'No finalized experiment is created until you approve this draft.',
      icon: status == 'awaiting_approval'
          ? Icons.verified_outlined
          : Icons.help_outline,
    );
  }
}

class _CopilotSection extends StatelessWidget {
  const _CopilotSection({required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(top: ResearchOsSpacing.md),
      child: ResearchOsCard(
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: Theme.of(context).textTheme.titleMedium),
            const SizedBox(height: ResearchOsSpacing.sm),
            ...children,
          ],
        ),
      ),
    );
  }
}

class _FactRow extends StatelessWidget {
  const _FactRow(this.label, this.value);

  final String label;
  final Object? value;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: ResearchOsSpacing.xs),
      child: Row(
        children: [
          Expanded(child: Text(label)),
          const SizedBox(width: ResearchOsSpacing.md),
          Flexible(
            child: Text(
              value == null || value.toString().isEmpty
                  ? 'Unknown'
                  : value.toString(),
              textAlign: TextAlign.end,
              overflow: TextOverflow.ellipsis,
            ),
          ),
        ],
      ),
    );
  }
}

class _CopilotListSection extends StatelessWidget {
  const _CopilotListSection({
    required this.title,
    required this.items,
    required this.label,
  });

  final String title;
  final List<Map<String, dynamic>> items;
  final String label;

  @override
  Widget build(BuildContext context) {
    return _CopilotSection(
      title: title,
      children: [
        if (items.isEmpty)
          const Text('None detected.')
        else
          Wrap(
            spacing: ResearchOsSpacing.sm,
            runSpacing: ResearchOsSpacing.sm,
            children: [
              for (final item in items)
                Chip(
                  label: Text(item[label]?.toString() ?? 'Unknown'),
                  avatar: Icon(
                    _confidenceIcon(item['confidence']?.toString()),
                    size: 16,
                  ),
                ),
            ],
          ),
      ],
    );
  }
}

class _CopilotTimeline extends StatelessWidget {
  const _CopilotTimeline({required this.events});

  final List<Map<String, dynamic>> events;

  @override
  Widget build(BuildContext context) {
    return _CopilotSection(
      title: 'Timeline Preview',
      children: [
        if (events.isEmpty)
          const Text('No timeline events detected.')
        else
          for (final event in events.take(12))
            Material(
              color: Colors.transparent,
              child: ListTile(
                contentPadding: EdgeInsets.zero,
                leading: Icon(event['source'] == 'inherited'
                    ? Icons.account_tree_outlined
                    : Icons.event_note_outlined),
                title: Text(event['title']?.toString() ?? 'Event'),
                subtitle: Text([
                  event['source'] == 'inherited' ? 'Inherited' : 'Experiment',
                  event['day'] == null ? null : 'D${event['day']}',
                  event['event_type'],
                ].whereType<Object>().join(' · ')),
              ),
            ),
      ],
    );
  }
}

class _ClarificationCards extends StatelessWidget {
  const _ClarificationCards({
    required this.questions,
    required this.controllers,
    required this.onSubmit,
    required this.loading,
  });

  final List<Map<String, dynamic>> questions;
  final Map<String, TextEditingController> controllers;
  final VoidCallback onSubmit;
  final bool loading;

  @override
  Widget build(BuildContext context) {
    if (questions.isEmpty) {
      return const SizedBox.shrink();
    }
    return _CopilotSection(
      title: 'Clarification Questions',
      children: [
        for (final question in questions)
          Padding(
            padding: const EdgeInsets.only(bottom: ResearchOsSpacing.sm),
            child: TextField(
              controller:
                  controllers[question['question_id']?.toString() ?? ''],
              decoration: InputDecoration(
                labelText: question['question']?.toString() ?? 'Question',
                helperText: question['reason']?.toString(),
                border: const OutlineInputBorder(),
              ),
            ),
          ),
        Align(
          alignment: Alignment.centerRight,
          child: OutlinedButton.icon(
            onPressed: loading ? null : onSubmit,
            icon: const Icon(Icons.question_answer_outlined),
            label: const Text('Apply answers'),
          ),
        ),
      ],
    );
  }
}

class _EvidenceCards extends StatelessWidget {
  const _EvidenceCards({required this.evidence});

  final List<Map<String, dynamic>> evidence;

  @override
  Widget build(BuildContext context) {
    return _CopilotSection(
      title: 'Evidence',
      children: [
        if (evidence.isEmpty)
          const Text('No extracted evidence.')
        else
          for (final item in evidence.take(8))
            Padding(
              padding: const EdgeInsets.only(bottom: ResearchOsSpacing.sm),
              child: Material(
                color: Colors.transparent,
                child: ListTile(
                  contentPadding: EdgeInsets.zero,
                  leading:
                      Icon(_confidenceIcon(item['confidence']?.toString())),
                  title: Text('${item['field']}: ${item['value']}'),
                  subtitle: Text(item['evidence']?.toString() ?? ''),
                ),
              ),
            ),
      ],
    );
  }
}

List<Map<String, dynamic>> _maps(Object? value) {
  if (value is! List) return const [];
  return value
      .whereType<Map>()
      .map((item) => item.map((key, val) => MapEntry(key.toString(), val)))
      .toList();
}

IconData _confidenceIcon(String? confidence) {
  switch (confidence) {
    case 'High':
      return Icons.check_circle_outline;
    case 'Medium':
      return Icons.adjust_outlined;
    case 'Low':
      return Icons.error_outline;
    default:
      return Icons.help_outline;
  }
}

class _FutureCreationMode extends StatelessWidget {
  const _FutureCreationMode({required this.mode, required this.onBack});

  final String mode;
  final VoidCallback onBack;

  @override
  Widget build(BuildContext context) {
    final isImport = mode == 'import';
    return Scaffold(
      appBar: AppBar(
        title: Text(isImport ? 'Import Spreadsheet' : 'Describe Experiment'),
        leading: BackButton(onPressed: onBack),
      ),
      body: SafeArea(
        child: ListView(
          padding: ResearchOsSpacing.screen,
          children: [
            ResearchOsEmptyState(
              title: isImport
                  ? 'Spreadsheet import is future-ready'
                  : 'Experiment extraction is future-ready',
              message: isImport
                  ? 'Mundi will later preview mapped spreadsheet columns and wait for confirmation before creating structured design data.'
                  : 'Mundi will later draft cohorts, conditions, interventions, and events from text or voice. Nothing will become active without researcher confirmation.',
              icon: isImport
                  ? Icons.table_chart_outlined
                  : Icons.auto_awesome_outlined,
            ),
          ],
        ),
      ),
    );
  }
}

class _ChipInput extends StatefulWidget {
  const _ChipInput({
    required this.label,
    required this.values,
    required this.onChanged,
  });

  final String label;
  final List<String> values;
  final VoidCallback onChanged;

  @override
  State<_ChipInput> createState() => _ChipInputState();
}

class _ChipInputState extends State<_ChipInput> {
  final _controller = TextEditingController();

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  void _add() {
    final pieces = _controller.text
        .split(',')
        .map((item) => item.trim())
        .where((item) => item.isNotEmpty);
    for (final piece in pieces) {
      if (!widget.values
          .any((item) => item.toLowerCase() == piece.toLowerCase())) {
        widget.values.add(piece);
      }
    }
    _controller.clear();
    widget.onChanged();
  }

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: ResearchOsSpacing.md),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: TextField(
                  controller: _controller,
                  textInputAction: TextInputAction.done,
                  onSubmitted: (_) => _add(),
                  decoration: InputDecoration(
                    labelText: widget.label,
                    hintText: 'Add one or comma-separated values',
                    border: const OutlineInputBorder(),
                  ),
                ),
              ),
              const SizedBox(width: ResearchOsSpacing.sm),
              IconButton.filled(
                tooltip: 'Add ${widget.label}',
                onPressed: _add,
                icon: const Icon(Icons.add),
              ),
            ],
          ),
          if (widget.values.isNotEmpty) ...[
            const SizedBox(height: ResearchOsSpacing.sm),
            Wrap(
              spacing: ResearchOsSpacing.sm,
              runSpacing: ResearchOsSpacing.sm,
              children: [
                for (final value in widget.values)
                  InputChip(
                    label: Text(value),
                    onDeleted: () {
                      widget.values.remove(value);
                      widget.onChanged();
                    },
                  ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

String _summaryList(Object? value) {
  if (value is List && value.isNotEmpty) {
    return value.join(', ');
  }
  return 'TBD';
}
