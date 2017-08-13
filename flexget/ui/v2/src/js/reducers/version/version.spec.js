import reducer from 'reducers/version';
import { GET_VERSION } from 'actions/version';

describe('reducers/auth', () => {
  it('should return the initial state', () => {
    expect(reducer(undefined, {})).toMatchSnapshot();
  });

  it('should login on LOGIN', () => {
    expect(reducer(undefined, {
      type: GET_VERSION,
      payload: {
        api_version: '1.1.2',
        flexget_version: '2.10.11',
        latest_version: '2.10.60',
      },
    })).toMatchSnapshot();
  });
});