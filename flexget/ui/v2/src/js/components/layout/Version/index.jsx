import React, { Component } from 'react';
import PropTypes from 'prop-types';
import semver from 'semver-compare';
import IconButton from 'material-ui/IconButton';
import Icon from 'material-ui/Icon';
import { Wrapper, Line, version } from 'components/layout/Version/styles';
import 'font-awesome/css/font-awesome.css';

class Version extends Component {
  static propTypes = {
    version: PropTypes.shape({
      api: PropTypes.string,
      flexget: PropTypes.string,
      latest: PropTypes.string,
    }).isRequired,
    getVersion: PropTypes.func.isRequired,
    className: PropTypes.string,
  };

  static defaultProps = {
    className: '',
  };

  componentDidMount() {
    this.props.getVersion();
  }

  render() {
    const { version: { api, flexget, latest }, className } = this.props;
    return (
      <Wrapper className={className}>
        <Line>Version Info</Line>
        <Line>Flexget: { flexget } {
          latest && semver(latest, flexget) === 1 && (
            <IconButton href="https://flexget.com/ChangeLog">
              <Icon className={`fa fa-question-circle-o ${version}`} />
            </IconButton>
          ) } </Line>
        <Line>API: { api }</Line>
      </Wrapper>
    );
  }
}

export default Version;
