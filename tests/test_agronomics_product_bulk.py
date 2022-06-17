# This file is part agronomics_product_bulk module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.
import unittest


from trytond.tests.test_tryton import ModuleTestCase
from trytond.tests.test_tryton import suite as test_suite


class AgronomicsProductBulkTestCase(ModuleTestCase):
    'Test Agronomics Product Bulk module'
    module = 'agronomics_product_bulk'


def suite():
    suite = test_suite()
    suite.addTests(unittest.TestLoader().loadTestsFromTestCase(
            AgronomicsProductBulkTestCase))
    return suite
