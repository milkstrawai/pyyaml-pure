
'''specific pyyaml-pure tests'''

import pytest
import yaml
import itertools

data_for_test = [ 2, +1, 0, -1, -2, '5', '-5', 'a b c', 2.2, +1.1, 0.0, -1.1, -2.2, { 'a':22, }, ]

class TestSafeDumpLoad:
	'''Test consistency of yaml.safe_dump and yaml.safe_load'''

	def test_safe_load(self):
		'''test yaml.safe_load()'''
		actual   = yaml.safe_load("- 2\n- 1\n\n- 0\n- -1\n- -2\n- '5'\n- '-5'\n- a b c\n- 2.2\n- 1.1\n- 0.0\n- -1.1\n- -2.2\n- a: 22\n")
		expected = data_for_test
		assert expected == actual, f'\n{repr(expected)}\n!=\n{repr(actual)}'

	def test_safe_dump(self):
		'''test yaml.safe_dump()'''
		for data, expected in [
			[ { 'a':2, 'b':'c' }, 'a: 2\nb: c\n', ],
			[ {}, '{}\n', ], [ {'a':{}}, 'a: {}\n', ],
			[ [], '[]\n', ], [ [[]]    , '- []\n', ],
			[ data_for_test, "- 2\n- 1\n- 0\n- !!int'-1'\n- !!int'-2'\n- '5'\n- '-5'\n- a b c\n- 2.2\n- 1.1\n- 0.0\n- !!float'-1.1'\n- !!float'-2.2'\n- a: 22\n", ],
		]:
			actual = yaml.safe_dump(data)
			assert expected == actual, f'\n{repr(expected)}\n!=\n{repr(actual)}'

	def test_safe_dump_load(self):
		'''test yaml.safe_dump() followed by yaml.safe_load(). should build itentical data'''

		load_kwargs = {}
		
		gen_paire     = lambda k: lambda v: [ k, v, ]
		default_value = object()
		clean_paires  = lambda paires: filter(lambda paire: paire[1] is not default_value, paires)
		to_dict       = lambda paires: dict(clean_paires(paires))

		for dump_kwargs in map(to_dict, itertools.product(
			map(gen_paire('comments')          , [ default_value, False, True, ]),
			map(gen_paire('default_style')     , [ default_value, "'", '"', '|', '>', ]),
			map(gen_paire('default_flow_style'), [ default_value, False, True, ]),
			map(gen_paire('canonical')         , [ default_value, False, True, ]),
			map(gen_paire('line_break')        , [ default_value, '\n', '\r\n', ]),
			map(gen_paire('explicit_start')    , [ default_value, False, True, ]),
			map(gen_paire('explicit_end')      , [ default_value, False, True, ]),
			map(gen_paire('version')           , [ default_value, [ 1,1, ], [ 1,2, ], ]),
			map(gen_paire('sort_keys')         , [ default_value, False, True, ]),
		)):
#			for load_kwargs in map(to_dict, itertools.product(
#				map(gen_paire('comments'), [ default_value, False, True, ]),
#			)):
				for data in [
					{}, { 'a':{}, }, { 'b':{}, 'a':[], },
					[], [ [], ]    , [ [], {}, ],
					data_for_test,
				]:
					try: mid_value = yaml.safe_dump(data, **dump_kwargs)
					except:
						print(f'{data=}\n{dump_kwargs=}')
						raise

					try: actual = yaml.safe_load(mid_value, **load_kwargs)
					except:
						print(f'{data=}\n{dump_kwargs=}\n{mid_value=}\n{load_kwargs=}')
						raise

					if load_kwargs.get('sort_keys', False): print('todo : maybe do some kind of sort on "expected"')
					expected = data
					assert expected == actual, f'inconsistent result with {dump_kwargs=} and {load_kwargs=}:\n{repr(expected)}\n!=\n{repr(actual)}'

