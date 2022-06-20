# This file is part agronomics_product_bulk module for Tryton.
# The COPYRIGHT file at the top level of this repository contains
# the full copyright notices and license terms.


from trytond.tests.test_tryton import ModuleTestCase
from trytond.modules.company.tests import CompanyTestMixin


class AgronomicsProductBulkTestCase(CompanyTestMixin, ModuleTestCase):
    'Test Agronomics Product Bulk module'
    module = 'agronomics_product_bulk'


del ModuleTestCase
