// Copyright 2013 Viewfinder. All rights reserved.
// Author: Spencer Kimball.

#import "PhysicsModel.h"

const float PhysicsModel::kFrictionCoeff_ = 600;     // coefficient of friction for releases
const float PhysicsModel::kEpsilon_ = 0.0001;
const double PhysicsModel::kDeltaTime_ = 0.005;      // granularity of simulation in seconds
const double PhysicsModel::kMaxSimulationTime_ = 5;  // maximum running time of simulation

PhysicsModel::PhysicsModel() {
  Reset(Vector2f(0, 0), Vector2f(0, 0));
}

void PhysicsModel::Reset() {
  accels_.clear();
  filters_.clear();
  start_time_ = WallTime_Now();
  last_time_ = start_time_;
  state_.p = Vector2f(0, 0);
  state_.v = Vector2f(0, 0);
  exit_condition_ = nil;
}

void PhysicsModel::Reset(const Vector2f& location, const Vector2f& velocity) {
  accels_.clear();
  filters_.clear();
  start_time_ = WallTime_Now();
  last_time_ = start_time_;
  state_.p = location;
  state_.v = velocity;
  exit_condition_ = nil;
}

bool PhysicsModel::RunModel(Vector2f* prev_loc, Vector2f* new_loc, WallTime now) {
  if (!now) {
    now = WallTime_Now();
  }
  if (accels_.empty()) {
    *prev_loc = state_.p;
    *new_loc = state_.p;
    return true;
  }
  if (now - last_time_ < kEpsilon_) {
    *prev_loc = state_.p;
    *new_loc = state_.p;
    return false;
  }
  // WallTime prev_time = last_time_;
  State prev_state = state_;
  Vector2f a;
  while (last_time_ < now) {
    const double dt = std::min<double>(kDeltaTime_, now - last_time_);
    a = Integrate(&state_, (last_time_ - start_time_), dt);
    last_time_ += dt;
  }
  bool complete;
  if (exit_condition_) {
    complete = exit_condition_(&state_, prev_state, last_time_, a);
  } else {
    complete = DefaultExitCondition(&state_, prev_state, last_time_, a) ||
               now - start_time_ > kMaxSimulationTime_;
  }
  *prev_loc = prev_state.p;
  *new_loc = state_.p;
  // LOG("prev: %s, cur: %s, v: %s, dt: %f", *prev_loc, state_.p, state_.v, (now - prev_time));
  return complete;
}

PhysicsModel::LocationFunc PhysicsModel::StaticLocation(
    const Vector2f& spring_loc) {
  Vector2f sl = spring_loc;
  return [^(const State& state, double t) {
      return sl;
    } copy];
}

void PhysicsModel::AddSpring(
    LocationFunc spring_loc, float spring_force, float damp_force) {
  AddSpringWithDampening(spring_loc, spring_force, damp_force);
}

void PhysicsModel::AddDefaultSpring(LocationFunc spring_loc) {
  const float kSpringForce = 100;
  const float kDampeningForce = 20;
  AddSpringWithDampening(spring_loc, kSpringForce, kDampeningForce);
}

void PhysicsModel::AddQuickSpring(LocationFunc spring_loc) {
  const float kSpringForce = 500;
  const float kDampeningForce = 50;
  AddSpringWithDampening(spring_loc, kSpringForce, kDampeningForce);
}

void PhysicsModel::AddSlowSpring(LocationFunc spring_loc) {
  const float kSpringForce = 10;
  const float kDampeningForce = 5;
  AddSpringWithDampening(spring_loc, kSpringForce, kDampeningForce);
}

void PhysicsModel::AddVeryQuickSpring(LocationFunc spring_loc) {
  const float kSpringForce = 750;
  const float kDampeningForce = 55;
  AddSpringWithDampening(spring_loc, kSpringForce, kDampeningForce);
}

void PhysicsModel::AddAccelerationFunction(AccelerationFunc func) {
  accels_.push_back(func);
}

void PhysicsModel::AddReleaseDeceleration() {
  AddFrictionalDeceleration(kFrictionCoeff_);
}

void PhysicsModel::AddAccelerationFilter(AccelerationFilter filter) {
  filters_.push_back(filter);
}

void PhysicsModel::SetExitCondition(ExitConditionFunc exit_func) {
  exit_condition_ = exit_func;
}

bool PhysicsModel::DefaultExitCondition(
    State* state, const State& prev_state,
    double t, const Vector2f& a) {
  return state->v.equal(Vector2f(0, 0), 1) && state->p.equal(prev_state.p, 1);
}

void PhysicsModel::AddSpringWithDampening(
    LocationFunc spring_loc, const float spring_force, const float dampening_force) {
  const Vector2f k = -Vector2f(spring_force, spring_force);
  const Vector2f b = -Vector2f(dampening_force, dampening_force);

  accels_.push_back(^(const State& state, double t) {
      return k * (state.p - spring_loc(state, t)) + b * state.v;
    });
}

void PhysicsModel::AddFrictionalDeceleration(float mu) {
  accels_.push_back(^(const State& state, double t) {
      return Vector2f(state.v(0) == 0 ? 0 : (state.v(0) > 0 ? -mu : mu),
                      state.v(1) == 0 ? 0 : (state.v(1) > 0 ? -mu : mu));
    });
}

PhysicsModel::Derivative PhysicsModel::Evaluate(
    const State &initial, double t, double dt, const Derivative &d) {
  State state;
  state.p = initial.p + d.dp * dt;
  state.v = initial.v + d.dv * dt;

  Derivative output;
  output.dp = state.v;

  // Compute dv from constituent accelerations.
  output.dv = Vector2f(0, 0);
  for (std::list<AccelerationFunc>::iterator iter = accels_.begin();
       iter != accels_.end();
       ++iter) {
    output.dv += (*iter)(state, t);
  }
  for (std::list<AccelerationFilter>::iterator iter = filters_.begin();
       iter != filters_.end();
       ++iter) {
    output.dv = (*iter)(state, t, output.dv);
  }
  return output;
}

Vector2f PhysicsModel::Integrate(State* state, double t, double dt) {
  Derivative a = Evaluate(*state, t, 0, Derivative());
  Derivative b = Evaluate(*state, t, dt * 0.5, a);
  Derivative c = Evaluate(*state, t, dt * 0.5, b);
  Derivative d = Evaluate(*state, t, dt, c);

  const Vector2f dpdt = (a.dp + (b.dp + c.dp) * 2.0 + d.dp) * 1.0 / 6.0;
  const Vector2f dvdt = (a.dv + (b.dv + c.dv) * 2.0 + d.dv) * 1.0 / 6.0;

  state->p = state->p + dpdt * dt;
  state->v = state->v + dvdt * dt;
  return dvdt;
}
