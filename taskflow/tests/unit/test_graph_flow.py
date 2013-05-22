# -*- coding: utf-8 -*-

# vim: tabstop=4 shiftwidth=4 softtabstop=4

#    Copyright (C) 2012 Yahoo! Inc. All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

import collections
import functools
import unittest

from taskflow import exceptions as excp
from taskflow import states
from taskflow import task
from taskflow import wrappers

from taskflow.patterns import graph_flow as gw


def null_functor(*args, **kwargs):
    return None


class ProvidesRequiresTask(task.Task):
    def __init__(self, name, provides, requires):
        super(ProvidesRequiresTask, self).__init__(name)
        self._provides = provides
        self._requires = requires

    def requires(self):
        return self._requires

    def provides(self):
        return self._provides

    def apply(self, context, *args, **kwargs):
        outs = {
            '__inputs__': dict(kwargs),
        }
        context['__order__'].append(self.name)
        for v in self.provides():
            outs[v] = True
        return outs


class GraphFlowTest(unittest.TestCase):
    def testRevertPath(self):
        flo = gw.Flow("test-flow")
        reverted = []

        def run1(context, *args, **kwargs):
            return {
                'a': 1,
            }

        def run1_revert(context, result, cause):
            reverted.append('run1')
            self.assertEquals(states.REVERTING, cause.flow.state)
            self.assertEquals(result, {'a': 1})

        def run2(context, a, *args, **kwargs):
            raise Exception('Dead')

        flo.add(wrappers.FunctorTask(None, run1, run1_revert,
                                     provides_what=['a'],
                                     extract_requires=True))
        flo.add(wrappers.FunctorTask(None, run2, null_functor,
                                     provides_what=['c'],
                                     extract_requires=True))

        self.assertEquals(states.PENDING, flo.state)
        self.assertRaises(Exception, flo.run, {})
        self.assertEquals(states.FAILURE, flo.state)
        self.assertEquals(['run1'], reverted)

    def testNoProvider(self):
        flo = gw.Flow("test-flow")
        flo.add(ProvidesRequiresTask('test1',
                                     provides=['a', 'b'],
                                     requires=['c', 'd']))
        self.assertEquals(states.PENDING, flo.state)
        self.assertRaises(excp.InvalidStateException, flo.run, {})
        self.assertEquals(states.FAILURE, flo.state)

    def testLoopFlow(self):
        flo = gw.Flow("test-flow")
        flo.add(ProvidesRequiresTask('test1',
                                     provides=['a', 'b'],
                                     requires=['c', 'd', 'e']))
        flo.add(ProvidesRequiresTask('test2',
                                     provides=['c', 'd', 'e'],
                                     requires=['a', 'b']))
        ctx = collections.defaultdict(list)
        self.assertEquals(states.PENDING, flo.state)
        self.assertRaises(excp.InvalidStateException, flo.run, ctx)
        self.assertEquals(states.FAILURE, flo.state)

    def testComplicatedInputsOutputs(self):
        flo = gw.Flow("test-flow")
        flo.add(ProvidesRequiresTask('test1',
                                     provides=['a', 'b'],
                                     requires=['c', 'd', 'e']))
        flo.add(ProvidesRequiresTask('test2',
                                     provides=['c', 'd', 'e'],
                                     requires=[]))
        flo.add(ProvidesRequiresTask('test3',
                                     provides=['c', 'd'],
                                     requires=[]))
        flo.add(ProvidesRequiresTask('test4',
                                     provides=['z'],
                                     requires=['a', 'b', 'c', 'd', 'e']))
        flo.add(ProvidesRequiresTask('test5',
                                     provides=['y'],
                                     requires=['z']))
        flo.add(ProvidesRequiresTask('test6',
                                     provides=[],
                                     requires=['y']))

        self.assertEquals(states.PENDING, flo.state)
        ctx = collections.defaultdict(list)
        flo.run(ctx)
        self.assertEquals(states.SUCCESS, flo.state)
        run_order = ctx['__order__']

        # Order isn't deterministic so that's why we sort it
        self.assertEquals(['test2', 'test3'], sorted(run_order[0:2]))

        # This order is deterministic
        self.assertEquals(['test1', 'test4', 'test5', 'test6'], run_order[2:])

    def testConnectRequirementFailure(self):

        def run1(context, *args, **kwargs):
            return {
                'a': 1,
            }

        def run2(context, b, c, d, *args, **kwargs):
            return None

        flo = gw.Flow("test-flow")
        flo.add(wrappers.FunctorTask(None, run1, null_functor,
                                     provides_what=['a'],
                                     extract_requires=True))
        flo.add(wrappers.FunctorTask(None, run2, null_functor,
                                     extract_requires=True))

        self.assertRaises(excp.InvalidStateException, flo.connect)
        self.assertRaises(excp.InvalidStateException, flo.run, {})
        self.assertRaises(excp.InvalidStateException, flo.order)

    def testHappyPath(self):
        flo = gw.Flow("test-flow")

        run_order = []
        f_args = {}

        def run1(context, *args, **kwargs):
            run_order.append('ran1')
            return {
                'a': 1,
            }

        def run2(context, a, *args, **kwargs):
            run_order.append('ran2')
            return {
                'c': 3,
            }

        def run3(context, a, *args, **kwargs):
            run_order.append('ran3')
            return {
                'b': 2,
            }

        def run4(context, b, c, *args, **kwargs):
            run_order.append('ran4')
            f_args['b'] = b
            f_args['c'] = c

        flo.add(wrappers.FunctorTask(None, run1, null_functor,
                                     provides_what=['a'],
                                     extract_requires=True))
        flo.add(wrappers.FunctorTask(None, run2, null_functor,
                                     provides_what=['c'],
                                     extract_requires=True))
        flo.add(wrappers.FunctorTask(None, run3, null_functor,
                                     provides_what=['b'],
                                     extract_requires=True))
        flo.add(wrappers.FunctorTask(None, run4, null_functor,
                                     extract_requires=True))

        flo.run({})
        self.assertEquals(['ran1', 'ran2', 'ran3', 'ran4'], sorted(run_order))
        self.assertEquals('ran1', run_order[0])
        self.assertEquals('ran4', run_order[-1])
        self.assertEquals({'b': 2, 'c': 3}, f_args)