from apscheduler.datastores.sqlalchemy import SQLAlchemyDataStore
import inspect

sig = inspect.signature(SQLAlchemyDataStore.__init__)
print('SQLAlchemyDataStore parameters:')
for name, param in sig.parameters.items():
    if name != 'self':
        default = param.default if param.default is not param.empty else "required"
        print(f'  - {name}: {default}')
