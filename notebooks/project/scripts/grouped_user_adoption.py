"""Validate an explicit user adoption; never relabel failed performance as passed."""
import ast
from pathlib import Path
from scripts.prepare_sequential_rounds import read, digest
from scripts.sequential_rounds import approval, checked_evidence, model_lock


def validate_user_adoption(base, value):
    from scripts.grouped_rounds import source_lock
    if (value.get('completion_kind') != 'explicit_user_adoption'
            or value.get('rounds') != [2, 3] or value.get('status') != 'complete'
            or value.get('performance_targets_met') is not False):
        raise ValueError('Wrong explicit stage-2 adoption scope')
    review = read(checked_evidence(value['evaluation']))
    approved = approval(checked_evidence(value['approval']), 'adopt_model_close_group', 2,
        dict(rounds=[2, 3], model=value['model'], code=value['code'],
             report_sha256=digest(value['evaluation']['path'])))
    if (approved.get('scope') != 'adopt_retrained_close_23_prepare_45'
            or approved.get('accept_recorded_regressions') is not True
            or approved.get('accept_target_shortfall') is not True
            or approved.get('start_next_tests') is not False):
        raise ValueError('Explicit adoption does not authorize this transition')
    if model_lock(Path(value['weights'])) != value['model'] or source_lock(value['code_root']) != value['code']:
        raise ValueError('Adopted code/model changed')
    required = {'training_result', 'training_runtime', 'training_release', 'checkpoint',
                'comparison_summary', 'epoch0', 'epoch1', 'pool', 'source_equivalence'}
    required.update(f'round_{n}_{kind}' for n in (1, 2, 3) for kind in ('report', 'execution_lock'))
    if not required <= review['evidence'].keys():
        raise ValueError('Adoption evidence incomplete')
    for item in review['evidence'].values():
        checked_evidence(item)
    runtime = read(review['evidence']['training_runtime']['path'])
    result = read(review['evidence']['training_result']['path'])
    if (result['exit_code'] != 0 or runtime['status'] != 'completed'
            or runtime['optimizer_steps'] != 46 or runtime['epochs_completed'] != 1
            or not runtime['validation_gate_passed']):
        raise ValueError('Adoption requires the completed targeted training job')
    summary = read(review['evidence']['comparison_summary']['path'])
    if summary['denominator'] != 3648 or summary['retrained_correct'] != review['field_correct']:
        raise ValueError('Cumulative adoption score changed')
    for n, count in ((1, 216), (2, 500), (3, 500)):
        report = read(review['evidence'][f'round_{n}_report']['path'])
        lock = read(review['evidence'][f'round_{n}_execution_lock']['path'])
        if (report['images'] != count or report['metrics']['field_total'] != 3*count
                or report['runtime']['status'] != 'completed' or not report['complete']
                or report['runtime'].get('failures') or report['metrics']['labels_without_predictions']
                or not report['metrics']['submission_format']['all_rows_compliant']
                or lock['model'] != value['model']):
            raise ValueError('Adoption cannot conceal missing/failed evaluation or a different model')
        if review['rounds'][str(n)] != dict(field_correct=report['metrics']['field_correct'],
                field_total=3*count, protected_field_losses=report['protected_field_losses'],
                all_targets_met=report['all_targets_met']):
            raise ValueError('Recorded regression/target result changed')
    equivalence = read(review['evidence']['source_equivalence']['path'])
    expected_sources = {name for name in value['code']
                        if name.startswith('notebooks/project/src/') and name.endswith('.py')}
    if set(equivalence['sources']) != expected_sources:
        raise ValueError('Inference equivalence coverage incomplete')
    for name, binding in equivalence['sources'].items():
        if (digest(Path(value['code_root']) / name) != binding['adopted_sha256']
                or digest(binding['evaluated_path']) != binding['evaluated_sha256']):
            raise ValueError('Inference source equivalence evidence changed')
        if ast.dump(ast.parse((Path(value['code_root']) / name).read_text(encoding='utf-8-sig'))) != ast.dump(
                ast.parse(Path(binding['evaluated_path']).read_text(encoding='utf-8-sig'))):
            raise ValueError('Adopted inference differs from the evaluated source')
    carry = read(checked_evidence(value['training_release']))
    pool = read(review['evidence']['pool']['path'])
    if (carry['admitted'] != pool['admitted'] or carry['group_roles'] != pool['group_roles']
            or carry['samples'] != pool['samples'] or carry.get('optimizer_execution_authorized') is not False):
        raise ValueError('Adopted carryover must preserve original roles and must not authorize training')
    registry = read(Path(base) / 'group_roles.json')
    if any(registry.get(group) != role for group, role in carry['group_roles'].items()):
        raise ValueError('Permanent validation role changed')
    return review
